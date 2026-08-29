#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Rattrapage des vignettes YouTube.

    python scripts/vignettes_youtube.py              # simulation
    python scripts/vignettes_youtube.py --ecrire     # télécharge et inscrit

À QUOI ÇA SERT
--------------
Les notules de vidéos importées AVANT que le champ « vignette » n'existe
n'ont pas d'image : dans le fil, elles n'affichent qu'un titre, parce que
l'illustration est cherchée dans le corps HTML et qu'une vidéo n'y a
qu'une iframe, sans image à extraire. Ce script comble le trou après coup,
sans réimporter les notules.

PAS BESOIN DE yt-dlp
--------------------
YouTube expose les vignettes à une adresse prévisible à partir du seul
identifiant de la vidéo. On essaie les définitions de la plus grande à la
plus petite et on garde la première qui répond vraiment :

    maxresdefault.jpg   1280x720, absente sur les vidéos anciennes
    sddefault.jpg        640x480
    hqdefault.jpg        480x360, toujours présente

Attention au piège : pour une définition absente, YouTube ne renvoie pas
toujours une erreur. Il sert parfois une image grise de remplacement, très
légère. On écarte donc aussi les réponses trop petites, sinon la moitié du
fil se retrouverait illustrée de rectangles gris.

OÙ VONT LES FICHIERS
--------------------
public/medias/youtube/<identifiant>.jpg, et le champ « vignette » de la
notule pointe sur /medias/youtube/<identifiant>.jpg. On rapatrie plutôt
que de pointer sur i.ytimg.com : une image distante disparaît le jour où
la chaîne change, et le site étant servi en https, tout appel en http
serait bloqué par le navigateur.

Ces fichiers JSON ne sont pas régénérés par migrate_dotclear.py (ils ne
viennent pas du dump) : les écrire directement est sans danger.
"""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

for flux in (sys.stdout, sys.stderr):
    try:
        flux.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

NOTULES = Path('src/content/notules')
VIGNETTES = Path('public/medias/youtube')

DEFINITIONS = ['maxresdefault', 'sddefault', 'hqdefault']

# En deçà, c'est l'image grise de remplacement de YouTube, pas la vignette.
TAILLE_MINIMALE = 3000

# Première image exploitable du corps, au sens exact où l'entend
# NotuleCard.astro : une <img> dont la largeur déclarée atteint 80 px, les
# plus petites étant des puces et des filets. Les deux logiques DOIVENT
# rester d'accord, faute de quoi le script poserait une vignette sur une
# notule que le fil illustre déjà de sa propre image.
IMAGE = re.compile(r'<img\b[^>]*>', re.I)
LARGEUR = re.compile(r'\bwidth\s*=\s*["\']?(\d+)', re.I)
SRC = re.compile(r'\bsrc\s*=\s*["\']([^"\']+)["\']', re.I)


def a_une_image(html_corps):
    for balise in IMAGE.findall(html_corps or ''):
        if not SRC.search(balise):
            continue
        largeur = LARGEUR.search(balise)
        if largeur and int(largeur.group(1)) < 80:
            continue
        return True
    return False


# Identifiant de vidéo dans une iframe, un lien, ou n'importe quelle forme
# d'adresse YouTube rencontrée dans le corps d'une notule.
DANS_LE_CORPS = re.compile(
    r'(?:youtube(?:-nocookie)?\.com/(?:embed|v)/|youtu\.be/|[?&]v=)'
    r'([A-Za-z0-9_-]{11})'
)


def identifiant(donnees):
    """
    Identifiant YouTube d'une notule.

    On regarde d'abord le champ « youtubeId » posé par l'importateur, puis,
    à défaut, le corps HTML : les toutes premières notules de vidéos ont pu
    être écrites avant que ce champ n'existe, et ne portent que leur iframe.
    """
    marque = donnees.get('youtubeId')
    if marque:
        return marque
    trouve = DANS_LE_CORPS.search(donnees.get('corpsHtml') or '')
    return trouve.group(1) if trouve else None


def telecharger(ident):
    """
    Renvoie (chemin_public, definition) ou (None, motif).
    """
    VIGNETTES.mkdir(parents=True, exist_ok=True)
    cible = VIGNETTES / f'{ident}.jpg'

    if cible.is_file() and cible.stat().st_size >= TAILLE_MINIMALE:
        return f'/medias/youtube/{ident}.jpg', 'déjà sur le disque'

    dernier = 'aucune définition disponible'
    for definition in DEFINITIONS:
        adresse = f'https://i.ytimg.com/vi/{ident}/{definition}.jpg'
        try:
            requete = Request(adresse, headers={'User-Agent': 'carnetsol'})
            with urlopen(requete, timeout=30) as reponse:
                donnees = reponse.read()
        except HTTPError as e:
            dernier = f'{definition} : erreur {e.code}'
            continue
        except (URLError, OSError) as e:
            dernier = f'{definition} : {e}'
            continue

        if len(donnees) < TAILLE_MINIMALE:
            dernier = f'{definition} : image de remplacement ({len(donnees)} o)'
            continue

        cible.write_bytes(donnees)
        return f'/medias/youtube/{ident}.jpg', definition

    return None, dernier


def verifier_gitignore():
    """
    Alerte si les vignettes sont exclues de Git.

    Le dépôt écarte souvent public/medias — la médiathèque pèse plusieurs
    gigaoctets et n'a rien à faire dans l'historique. Mais les vignettes,
    elles, sont minuscules et DOIVENT être publiées : exclues, elles
    resteraient sur votre disque, et le site afficherait des images
    brisées sans que rien ne l'annonce pendant la compilation.
    """
    exemple = next(VIGNETTES.glob('*.jpg'), None)
    if exemple is None:
        return
    try:
        resultat = subprocess.run(
            ['git', 'check-ignore', '-q', str(exemple)],
            capture_output=True, timeout=15)
    except (OSError, subprocess.SubprocessError):
        return

    if resultat.returncode == 0:
        print()
        print("!! ATTENTION — les vignettes sont exclues par .gitignore.")
        print(f"   {exemple} ne sera pas publié, et le site affichera des")
        print("   images brisées sans le signaler.")
        print("   Ajoutez cette exception à la fin de votre .gitignore :")
        print()
        print("       !public/medias/youtube/")
        print("       !public/medias/youtube/*.jpg")
        print()
    else:
        print()
        print("Vignettes suivies par Git : pensez à les valider.")
        print("   git add public/medias/youtube")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--ecrire', action='store_true')
    ap.add_argument('--meme-illustrees', dest='meme_illustrees',
                    action='store_true',
                    help="poser la vignette même sur les notules qui ont "
                         "déjà une image (elle la remplacera dans le fil)")
    ap.add_argument('--refaire', action='store_true',
                    help="retélécharger même les notules déjà pourvues")
    ap.add_argument('--depuis', type=int, default=150000,
                    help="ne considérer que les notules au-delà de cet "
                         "identifiant (défaut : 150000, la plage des vidéos)")
    args = ap.parse_args()

    if not NOTULES.is_dir():
        print(f"ARRÊT — {NOTULES} introuvable. Lancez le script depuis la "
              "racine du projet.")
        sys.exit(1)

    a_traiter, deja, sans_identifiant, illustrees = [], [], [], []

    for f in sorted(NOTULES.glob('*.json')):
        try:
            d = json.loads(f.read_text(encoding='utf-8'))
        except (json.JSONDecodeError, OSError):
            continue

        est_video = bool(d.get('youtubeId')) or int(d.get('postId', 0)) >= args.depuis
        ident = identifiant(d)

        if est_video:
            # Notule de vidéo : la vignette est son illustration naturelle.
            if not ident:
                sans_identifiant.append((f.name, d.get('titre', '')))
                continue
            genre = 'vidéo'
        elif ident:
            # Notule ordinaire citant une vidéo. On ne l'illustre QUE si
            # elle n'a pas d'image à elle : « vignette » prime sur la
            # fouille du corps dans NotuleCard, poser l'une écraserait
            # l'autre. La vignette comble un vide, elle ne remplace rien.
            if a_une_image(d.get('corpsHtml')) and not args.meme_illustrees:
                illustrees.append(d.get('titre', ''))
                continue
            genre = 'citant une vidéo'
        else:
            continue

        if d.get('vignette') and not args.refaire:
            deja.append(d.get('titre', ''))
            continue

        a_traiter.append((f, d, ident, genre))

    total = len(a_traiter) + len(deja) + len(sans_identifiant) + len(illustrees)
    print(f"Notules portant une vidéo : {total}")
    print(f"   déjà pourvues                 : {len(deja)}")
    print(f"   déjà illustrées, non touchées : {len(illustrees)}")
    print(f"   sans identifiant              : {len(sans_identifiant)}")
    print(f"   à traiter                     : {len(a_traiter)}")
    if a_traiter:
        notules_video = sum(1 for x in a_traiter if x[3] == 'vidéo')
        print(f"       dont notules de vidéo     : {notules_video}")
        print(f"       dont notules citant       : {len(a_traiter) - notules_video}")

    if sans_identifiant:
        print("\nSANS IDENTIFIANT REPÉRABLE — ni champ « youtubeId », ni "
              "adresse YouTube dans le corps :")
        for nom, titre in sans_identifiant[:10]:
            print(f"   {nom}  {titre[:56]}")

    if not a_traiter:
        print("\nRien à faire.")
        return

    print()
    for f, d, ident, genre in a_traiter[:15]:
        print(f"   {d.get('postId'):>7}  {ident}  [{genre}]  "
              f"{str(d.get('titre',''))[:42]}")
    if len(a_traiter) > 15:
        print(f"   … et {len(a_traiter) - 15} autres.")

    if not args.ecrire:
        print("\nSimulation. Relancez avec --ecrire pour télécharger.")
        return

    print("\nTéléchargement…")
    reussies, ratees = 0, []
    for f, d, ident, genre in a_traiter:
        chemin, detail = telecharger(ident)
        if chemin:
            d['vignette'] = chemin
            f.write_text(json.dumps(d, ensure_ascii=False, indent=1) + '\n',
                         encoding='utf-8')
            print(f"   ok      {ident}  ({detail})")
            reussies += 1
        else:
            print(f"   échec   {ident}  ({detail})")
            ratees.append((d.get('postId'), ident, genre,
                           d.get('titre', ''), d.get('url', ''), detail))

    print(f"\n{reussies} vignette(s) posée(s), {len(ratees)} échec(s).")

    if ratees:
        # Un identifiant nu ne dit rien : on rattache chaque échec à sa
        # notule, seule façon d'en juger.
        nôtres = [r for r in ratees if r[2] == 'vidéo']
        citees = [r for r in ratees if r[2] != 'vidéo']

        print()
        print("POURQUOI CES ÉCHECS")
        print("hqdefault.jpg existe pour TOUTE vidéo en ligne. Une erreur 404")
        print("sur cette définition signifie donc que la vidéo elle-même n'est")
        print("plus accessible : supprimée, passée en privé, ou compte fermé.")
        print("Le script n'y peut rien, et la notule reste intacte : elle")
        print("retombera sur son chapô dans le fil.")

        if citees:
            print(f"\nVIDÉOS CITÉES par des notules ordinaires ({len(citees)}) —")
            print("des vidéos d'autrui, disparues depuis. C'est le cas normal :")
            for pid, ident, _, titre, url, motif in citees[:15]:
                print(f"   {pid:>7}  {ident}  {titre[:52]}")
                print(f"            {url}")

        if nôtres:
            print(f"\n!! VIDÉOS DE VOTRE CHAÎNE ({len(nôtres)}) — celles-là")
            print("devraient exister. Vérifiez si elles sont en privé ou en")
            print("non répertorié, ou si l'identifiant a été mal repris :")
            for pid, ident, _, titre, url, motif in nôtres:
                print(f"   {pid:>7}  {ident}  {titre[:52]}")
                print(f"            https://www.youtube.com/watch?v={ident}")

        rapport = Path('vignettes-manquantes.tsv')
        with rapport.open('w', encoding='utf-8', newline='') as sortie:
            sortie.write('postId\tidentifiant\tgenre\ttitre\turl\tmotif\n')
            for ligne in ratees:
                sortie.write('\t'.join(str(x) for x in ligne) + '\n')
        print(f"\nDétail complet : {rapport}")

    if reussies:
        verifier_gitignore()

    print("\nRelancez « npm run build », puis vérifiez la page d'accueil.")


if __name__ == '__main__':
    main()
