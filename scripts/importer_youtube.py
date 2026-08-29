#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Import des vidéos de la chaîne YouTube en notules.

    python scripts/importer_youtube.py                 # simulation
    python scripts/importer_youtube.py --ecrire        # applique

Conçu pour être RELANCÉ à chaque nouvelle publication : chaque notule
produite retient l'identifiant YouTube de sa vidéo, et le script ignore
tout ce qui est déjà importé. Un simple rappel après chaque mise en ligne
suffit donc à tenir le site à jour.

Dépendance : yt-dlp, qui doit être accessible dans le PATH.
    pip install -U yt-dlp

Les Shorts sont écartés : l'onglet /videos ne devrait pas en contenir,
mais le filtre sur la durée rattrape les cas où YouTube en laisse passer.

Pour travailler hors ligne (ou rejouer un import), on peut fournir un
fichier déjà produit par yt-dlp :
    yt-dlp --dump-json --skip-download "URL" > videos.jsonl
    python scripts/importer_youtube.py --depuis-json videos.jsonl
"""

import argparse
import html
import json
import re
import shutil
import subprocess
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import URLError, HTTPError
from urllib.request import Request, urlopen

for flux in (sys.stdout, sys.stderr):
    try:
        flux.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

CHAINE = 'https://www.youtube.com/@carnetsol/videos'
NOTULES = Path('src/content/notules')
CATEGORIES = Path('src/content/categories.json')

# Plage réservée aux vidéos. Assez haute pour que la numérotation des
# notules ordinaires (~3 500 aujourd'hui) ne la rattrape jamais.
PREMIER_ID = 150001

# Les vignettes sont rapatriées ici plutôt que servies depuis
# i.ytimg.com : une image en http:// depuis une page https serait bloquée
# par le navigateur, et une image distante disparaît le jour où la chaîne
# change. On la télécharge donc une fois pour toutes.
VIGNETTES = Path('public/medias/youtube')

CATEGORIE = {'nom': 'Les vidéos de Carnets sur sol',
             'slug': 'Les-videos-de-carnets-sur-sol'}

BANDEAU = ('Nouvelle publication de la chaîne YouTube de Carnets sur sol')

# En dessous de cette durée, on considère qu'il s'agit d'un Short.
DUREE_SHORT = 60


# ---------------------------------------------------------------- outils

def slugifier(valeur):
    """
    Reproduit slugifier() de src/lib/notules.ts. Les deux DOIVENT donner
    le même résultat : le site construit ses adresses avec la version
    TypeScript, ce script écrit le champ « url » avec celle-ci.
    """
    s = unicodedata.normalize('NFD', valeur)
    s = ''.join(c for c in s if unicodedata.category(c) != 'Mn')
    s = s.lower().replace('|', '-')
    s = re.sub(r'[^\w\s-]', '', s)
    s = s.strip()
    s = re.sub(r'[-\s]+', '-', s)
    return s.strip('-') or 'notule'


def texte_brut(html_source):
    return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', html_source)).strip()


def description_en_html(description):
    """
    La description YouTube est du texte brut. On échappe le HTML, on
    transforme les adresses en liens (sortants, donc nouvel onglet), et on
    coupe en paragraphes sur les lignes vides.
    """
    if not description or not description.strip():
        return ''

    blocs = re.split(r'\n\s*\n', description.strip())
    sortie = []
    for bloc in blocs:
        contenu = html.escape(bloc.strip())
        contenu = re.sub(
            r'(https?://[^\s<]+[^\s<.,;:!?)\]])',
            r'<a href="\1" target="_blank" rel="noopener noreferrer">\1</a>',
            contenu
        )
        contenu = contenu.replace('\n', '<br />\n')
        sortie.append(f'<p>{contenu}</p>')
    return '\n'.join(sortie)


def corps_html(video):
    """Bandeau + lecteur + description."""
    titre = html.escape(video['titre'], quote=True)
    return (
        f'<p class="recuperation">{BANDEAU}</p>\n'
        f'<figure class="video">\n'
        f'  <iframe src="https://www.youtube-nocookie.com/embed/{video["id"]}"\n'
        f'          title="{titre}" loading="lazy"\n'
        f'          allow="accelerometer; clipboard-write; encrypted-media; '
        f'picture-in-picture" allowfullscreen></iframe>\n'
        f'</figure>\n'
        f'{description_en_html(video["description"])}'
    )


def choisir_vignette(brut):
    """
    Meilleure vignette disponible. yt-dlp donne `thumbnail` (son choix) et
    `thumbnails` (toutes, avec largeurs). On prend la plus large, en
    écartant les images animées et les formats exotiques.
    """
    candidates = []
    for t in brut.get('thumbnails') or []:
        url = t.get('url') or ''
        if not url.startswith('http'):
            continue
        if '.webp' in url or 'animated' in url:
            continue
        candidates.append((t.get('width') or 0, url))
    if candidates:
        return max(candidates)[1]
    return brut.get('thumbnail') or ''


def telecharger_vignette(url, identifiant):
    """
    Renvoie le chemin public de la vignette, ou '' en cas d'échec.
    Un échec n'interrompt PAS l'import : la notule est créée sans image,
    ce qui vaut mieux que de perdre la vidéo pour un fichier manquant.
    """
    if not url:
        return ''
    VIGNETTES.mkdir(parents=True, exist_ok=True)
    cible = VIGNETTES / f'{identifiant}.jpg'
    if cible.is_file():
        return f'/medias/youtube/{identifiant}.jpg'
    try:
        requete = Request(url, headers={'User-Agent': 'carnetsol-import'})
        with urlopen(requete, timeout=30) as reponse:
            donnees = reponse.read()
        if len(donnees) < 1000:
            raise ValueError('image suspecte, trop petite')
        cible.write_bytes(donnees)
        return f'/medias/youtube/{identifiant}.jpg'
    except (URLError, HTTPError, OSError, ValueError) as erreur:
        print(f"      vignette non récupérée ({erreur})")
        return ''


def date_video(brut):
    """
    Date de publication. `timestamp` est préféré à `upload_date` : il porte
    l'heure, ce qui préserve l'ordre entre deux vidéos du même jour.
    """
    if brut.get('timestamp'):
        return datetime.fromtimestamp(brut['timestamp'], tz=timezone.utc)
    for champ in ('release_date', 'upload_date'):
        v = brut.get(champ)
        if v:
            return datetime.strptime(str(v), '%Y%m%d').replace(
                hour=12, tzinfo=timezone.utc)
    return None


# ------------------------------------------------------------- yt-dlp

# Emplacements fouillés quand yt-dlp n'est pas dans le PATH. Sous Windows
# on l'installe souvent en posant l'exécutable quelque part sans toucher au
# PATH : inutile de faire échouer le script pour si peu.
EMPLACEMENTS = [
    r'C:\yt-dlp.exe',
    r'C:\yt-dlp\yt-dlp.exe',
    r'C:\Program Files\yt-dlp\yt-dlp.exe',
    r'C:\Users\PC\yt-dlp.exe',
    '/usr/local/bin/yt-dlp',
]

_binaire_trouve = None


def trouver_ytdlp(indique=None):
    global _binaire_trouve
    if _binaire_trouve:
        return _binaire_trouve

    pistes = []
    if indique:
        pistes.append(indique)
    pistes += [shutil.which('yt-dlp'), shutil.which('yt-dlp.exe')]
    pistes += EMPLACEMENTS
    pistes.append(str(Path.home() / 'yt-dlp.exe'))

    for piste in pistes:
        if piste and Path(piste).is_file():
            _binaire_trouve = str(piste)
            return _binaire_trouve

    print("ARRÊT — yt-dlp introuvable.")
    print("        Cherché dans le PATH puis à ces emplacements :")
    for piste in EMPLACEMENTS:
        print("          " + piste)
    print("        Indiquez le chemin exact :")
    print('          python scripts/importer_youtube.py --ytdlp "C:\\yt-dlp.exe"')
    sys.exit(1)


def lancer_ytdlp(arguments):
    binaire = trouver_ytdlp()

    resultat = subprocess.run([binaire] + arguments,
                              capture_output=True, text=True,
                              encoding='utf-8', errors='replace')
    if resultat.returncode != 0:
        print("ARRÊT — yt-dlp a échoué :")
        for ligne in (resultat.stderr or '').splitlines()[-15:]:
            print('   ' + ligne)
        sys.exit(1)

    lignes = []
    for ligne in resultat.stdout.splitlines():
        ligne = ligne.strip()
        if ligne.startswith('{'):
            lignes.append(json.loads(ligne))
    return lignes


def lister_chaine(url):
    """Liste légère : identifiants, titres, durées. Rapide."""
    print(f"Inventaire de la chaîne… ({url})")
    return lancer_ytdlp(['--flat-playlist', '--dump-json',
                         '--ignore-errors', url])


def detailler(identifiants):
    """
    Métadonnées complètes, description comprise. Coûteux : on ne le fait
    que pour les vidéos réellement nouvelles.
    """
    fiches = []
    for i, ident in enumerate(identifiants, 1):
        print(f"   {i}/{len(identifiants)} — {ident}")
        lot = lancer_ytdlp(['--dump-json', '--skip-download', '--no-warnings',
                            f'https://www.youtube.com/watch?v={ident}'])
        fiches += lot
    return fiches


# ------------------------------------------------------------ principal

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--chaine', default=CHAINE)
    ap.add_argument('--ytdlp', help='chemin de yt-dlp.exe si absent du PATH')
    ap.add_argument('--depuis-json', help='fichier .jsonl produit par yt-dlp')
    ap.add_argument('--max', type=int, help='ne traiter que les N plus récentes')
    ap.add_argument('--duree-short', type=int, default=DUREE_SHORT)
    ap.add_argument('--sans-vignettes', action='store_true',
                    help="ne pas télécharger les vignettes des vidéos")
    ap.add_argument('--ecrire', action='store_true')
    args = ap.parse_args()

    if not NOTULES.is_dir():
        print(f"ARRÊT — {NOTULES} introuvable. Lancez le script depuis la "
              "racine du projet.")
        sys.exit(1)

    # Vérifié tout de suite : mieux vaut échouer avant de lire 3 500 fichiers.
    if not args.depuis_json:
        print(f"yt-dlp : {trouver_ytdlp(args.ytdlp)}")

    # --- état actuel du site --------------------------------------------
    deja, ids_pris, urls_prises = {}, set(), set()
    for f in NOTULES.glob('*.json'):
        d = json.loads(f.read_text(encoding='utf-8'))
        ids_pris.add(int(d['postId']))
        urls_prises.add(d['url'])
        if d.get('youtubeId'):
            deja[d['youtubeId']] = d['postId']

    print(f"Notules existantes    : {len(ids_pris)}")
    print(f"Vidéos déjà importées : {len(deja)}")
    print()

    # --- récupération ----------------------------------------------------
    if args.depuis_json:
        brutes = [json.loads(l) for l in
                  Path(args.depuis_json).read_text(encoding='utf-8').splitlines()
                  if l.strip().startswith('{')]
        print(f"Lu depuis {args.depuis_json} : {len(brutes)} fiches")
    else:
        inventaire = lister_chaine(args.chaine)
        print(f"Vidéos annoncées par la chaîne : {len(inventaire)}")

        candidates, shorts = [], []
        for v in inventaire:
            ident = v.get('id')
            if not ident:
                continue
            duree = v.get('duration')
            if '/shorts/' in (v.get('url') or '') or \
               (duree is not None and duree <= args.duree_short):
                shorts.append((ident, v.get('title', ''), duree))
                continue
            if ident in deja:
                continue
            candidates.append(ident)

        print(f"   Shorts écartés     : {len(shorts)}")
        print(f"   Déjà importées     : "
              f"{len(inventaire) - len(shorts) - len(candidates)}")
        print(f"   À traiter          : {len(candidates)}")
        if shorts:
            print("   (Shorts écartés, pour contrôle :)")
            for ident, titre, duree in shorts[:8]:
                print(f"      {ident}  {duree}s  {titre[:60]}")

        if not candidates:
            print("\nRien de nouveau.")
            return

        if args.max:
            candidates = candidates[:args.max]
        print("\nRécupération des descriptions…")
        brutes = detailler(candidates)

    # --- mise en forme ---------------------------------------------------
    videos, ecartees = [], []
    for b in brutes:
        ident = b.get('id')
        if not ident or ident in deja:
            continue
        duree = b.get('duration')
        if duree is not None and duree <= args.duree_short:
            ecartees.append((ident, 'short', b.get('title', '')))
            continue
        d = date_video(b)
        if not d:
            ecartees.append((ident, 'sans date', b.get('title', '')))
            continue
        videos.append({
            'id': ident,
            'titre': (b.get('title') or 'Sans titre').strip(),
            'description': b.get('description') or '',
            'date': d,
            'vignette_url': choisir_vignette(b),
        })

    # De la plus ancienne à la plus récente : les identifiants de notule
    # suivent ainsi l'ordre chronologique, comme dans le reste du site.
    videos.sort(key=lambda v: v['date'])

    prochain = max([PREMIER_ID - 1] + [i for i in ids_pris
                                       if i >= PREMIER_ID]) + 1

    fiches = []
    for v in videos:
        while prochain in ids_pris:
            prochain += 1
        d = v['date']
        slug = slugifier(v['titre'])
        url = (f"/css/{d.year}/{d.month:02d}/{d.day:02d}/"
               f"{prochain}-{slug}/")
        if url in urls_prises:
            ecartees.append((v['id'], 'adresse déjà prise', v['titre']))
            continue

        corps = corps_html(v)
        fiches.append({
            'postId': prochain,
            'titre': v['titre'],
            'slug': slug,
            'url': url,
            'date': d.isoformat(),
            'modifie': None,
            'auteur': 'DavidLeMarrec',
            'langue': 'fr',
            'categories': [CATEGORIE],
            'chapoHtml': '',
            'corpsHtml': corps,
            'notesHtml': '',
            'extrait': texte_brut(description_en_html(v['description']))[:300],
            'vignette': '',   # rempli à l'écriture, si le téléchargement réussit
            'nbCommentaires': 0,
            'commentaires': [],
            'epingle': False,
            # Marqueur de provenance : c'est lui qui évite les doublons
            # lors des relances. Ignoré par le schéma du site.
            'youtubeId': v['id'],
        })
        ids_pris.add(prochain)
        urls_prises.add(url)
        prochain += 1

    # --- rapport ---------------------------------------------------------
    print(f"\nNOTULES À CRÉER : {len(fiches)}")
    for f in fiches[:10]:
        print(f"   {f['postId']}  {f['date'][:10]}  {f['titre'][:64]}")
    if len(fiches) > 10:
        print(f"   … et {len(fiches) - 10} autres.")
    if ecartees:
        print(f"\nÉCARTÉES : {len(ecartees)}")
        for ident, motif, titre in ecartees[:10]:
            print(f"   {ident}  [{motif}]  {titre[:56]}")

    if not fiches:
        return

    if not args.ecrire:
        print("\nSimulation. Relancez avec --ecrire pour créer les fichiers.")
        return

    # --- écriture --------------------------------------------------------
    for f in fiches:
        cible = NOTULES / f"{f['postId']}.json"
        if cible.exists():
            print(f"   IGNORÉ (existe déjà) : {cible}")
            continue
        if not args.sans_vignettes:
            url = next((v['vignette_url'] for v in videos
                        if v['id'] == f['youtubeId']), '')
            f['vignette'] = telecharger_vignette(url, f['youtubeId'])
        cible.write_text(json.dumps(f, ensure_ascii=False, indent=1) + '\n',
                         encoding='utf-8')
    print(f"\n{len(fiches)} notule(s) écrite(s) dans {NOTULES}")

    # La catégorie doit exister, sinon les notules n'apparaîtront nulle part.
    if CATEGORIES.is_file():
        cats = json.loads(CATEGORIES.read_text(encoding='utf-8'))
        if not any(c['slug'] == CATEGORIE['slug'] for c in cats):
            cats.append({
                'id': max(int(c['id']) for c in cats) + 1,
                'nom': CATEGORIE['nom'],
                'description': '',
                'slug': CATEGORIE['slug'],
                # 2000+ : bloc des catégories non encore classées, cf.
                # scripts/ordonner_categories.py
                'ordre': 2000,
            })
            CATEGORIES.write_text(
                json.dumps(cats, ensure_ascii=False, indent=2) + '\n',
                encoding='utf-8')
            print(f"Catégorie « {CATEGORIE['nom']} » ajoutée à {CATEGORIES}.")
            print("Pensez à lui donner sa place dans "
                  "scripts/ordonner_categories.py.")

    print("\nRelancez « npm run build » pour vérifier.")


if __name__ == '__main__':
    main()
