#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Réparation des liens vers web.archive.org.

    python scripts/reparer_webarchive.py              # simulation
    python scripts/reparer_webarchive.py --ecrire     # applique

CE QUE VOTRE RAPPORT A MONTRÉ
-----------------------------
Sur 37 liens relevés dans 10 notules, un seul pointait vers une notule du
site. Les 36 autres visent YouTube, Spotify, Google Drive, des forums, des
magazines — enveloppés dans web.archive.org. C'est la signature de la
récupération HTTrack : Wayback réécrit TOUS les liens des pages qu'il
archive, y compris les liens sortants. Ces adresses n'ont donc jamais été
choisies, elles ont été subies.

Deux traitements, donc :
  - lien vers une notule du site  -> adresse interne (/css/AAAA/MM/JJ/…)
  - lien vers l'extérieur         -> on retire l'enveloppe Wayback et on
                                     rétablit l'adresse d'origine

Le second point mérite une seconde de réflexion : si le site visé a
disparu, l'archive était le seul accès. C'est pourquoi --garder-archive
permet de laisser les liens sortants tels quels et de ne réparer que les
liens internes.

COMMENT C'EST ÉCRIT
-------------------
Rien n'est modifié dans src/content/notules/ : ces fichiers sont
régénérés à chaque migration. Les réparations sont déposées dans
src/content/corrections/<postId>.json sous forme de « remplacements »,
appliqués au moment de la compilation. Un correctif déjà présent est
complété, jamais écrasé.
"""

import argparse
import json
import re
import sys
import unicodedata
from collections import Counter
from pathlib import Path
from urllib.parse import unquote

for flux in (sys.stdout, sys.stderr):
    try:
        flux.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

NOTULES = Path('src/content/notules')
CORRECTIONS = Path('src/content/corrections')

WAYBACK = re.compile(
    r'https?://(?:web\.)?archive\.org/web/\d{4,14}\w*/(https?[^\s"\'<>)]+)',
    re.I
)

# Seul /css/ a été migré dans ce site. Les autres blogs de la galaxie
# (/dss/ pour les disques, etc.) VIVENT TOUJOURS sur operacritiques.free.fr :
# leurs adresses doivent être désenveloppées, pas redirigées ici.
#
# C'est un piège qu'il faut nommer : les identifiants sont propres à chaque
# blog. Le billet 116 de /dss/ et la notule 116 de /css/ n'ont aucun rapport.
# Apparier par identifiant sans regarder le préfixe enverrait le lecteur sur
# un texte sans rapport — une erreur silencieuse, donc pire qu'un lien mort.
NOTULE = re.compile(
    r'/([a-z]{2,4})/(?:index\.php[/?])?(\d{4})/(\d{2})/(\d{2})/(\d+)(?:-([^/?#&"\']*))?',
    re.I
)

CHAMPS = ['corpsHtml', 'chapoHtml', 'notesHtml']

# Vos propres domaines, anciens et actuels. Un lien désenveloppé qui
# retombe là-dessus SANS correspondre à une notule est un orphelin :
# il pointera vers une page morte. Signalé à part pour que vous puissiez
# décider au cas par cas.
NOTRES = ('operacritiques.free.fr', 'carnetsol.fr', 'www.carnetsol.fr',
          'carnetsol.netlify.app', 'carnetsol.github.io')


def normaliser(slug):
    s = unquote(slug or '')
    s = unicodedata.normalize('NFD', s)
    s = ''.join(c for c in s if unicodedata.category(c) != 'Mn')
    return re.sub(r'[^a-z0-9]+', '-', s.lower()).strip('-')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--ecrire', action='store_true')
    ap.add_argument('--garder-archive', action='store_true',
                    help="ne réparer que les liens internes ; laisser les "
                         "liens sortants dans leur enveloppe Wayback")
    args = ap.parse_args()

    if not NOTULES.is_dir():
        print(f"ARRÊT — {NOTULES} introuvable. Lancez le script depuis la "
              "racine du projet.")
        sys.exit(1)

    # --- index du site ---------------------------------------------------
    par_slug, par_id, notules = {}, {}, []
    for f in sorted(NOTULES.glob('*.json')):
        d = json.loads(f.read_text(encoding='utf-8'))
        notules.append(d)
        par_slug[normaliser(d.get('slug', ''))] = d['url']
        par_id[int(d['postId'])] = d['url']

    # --- relevé et décision ----------------------------------------------
    # postId -> { adresse Wayback complète : adresse de remplacement }
    plan = {}
    stats = Counter()
    exemples = []
    orphelins = []

    for d in notules:
        for champ in CHAMPS:
            texte = d.get(champ) or ''
            for m in WAYBACK.finditer(texte):
                complet = m.group(0)
                origine = m.group(1)

                n = NOTULE.search(origine)
                cible = None
                # Le préfixe doit être /css/ : c'est le seul blog migré ici.
                if n and n.group(1).lower() == 'css':
                    slug = normaliser(n.group(6) or '')
                    if slug and slug in par_slug:
                        cible, verdict = par_slug[slug], 'INTERNE_SLUG'
                    elif int(n.group(5)) in par_id:
                        cible, verdict = par_id[int(n.group(5))], 'INTERNE_ID'

                if cible is None:
                    if args.garder_archive:
                        stats['LAISSE'] += 1
                        continue
                    hote = re.match(r'https?://([^/:?#]+)', origine)
                    # Orphelin = adresse d'une notule de /css/ qui n'existe
                    # plus. Un lien vers /dss/ ou un autre blog encore en
                    # ligne n'est pas orphelin : il est simplement sortant.
                    orphelin = (
                        hote and hote.group(1).lower() in NOTRES
                        and n and n.group(1).lower() == 'css'
                    )
                    cible = origine
                    verdict = 'INTERNE_ORPHELIN' if orphelin else 'DESENVELOPPE'
                    if orphelin:
                        orphelins.append((d['postId'], origine))

                stats[verdict] += 1
                plan.setdefault(d['postId'], {})[complet] = cible
                if len(exemples) < 12:
                    exemples.append((d['postId'], verdict, complet, cible))

    total = sum(stats.values())
    print(f"Notules examinées : {len(notules)}")
    print(f"Liens Wayback     : {total}")
    for k in ('INTERNE_SLUG', 'INTERNE_ID', 'DESENVELOPPE',
              'INTERNE_ORPHELIN', 'LAISSE'):
        if stats[k]:
            print(f"   {k:<18} {stats[k]:>4}")

    if orphelins:
        print("\nORPHELINS — adresses de vos propres blogs sans notule "
              "correspondante.")
        print("Désenveloppées, elles pointeront vers une page morte ; à "
              "revoir à la main :")
        for pid, url in orphelins:
            print(f"   notule {pid} : {url[:120]}")

    if not plan:
        print("\nRien à réparer.")
        return

    print(f"\nNOTULES CONCERNÉES : {len(plan)}")
    for pid, remplacements in sorted(plan.items()):
        print(f"   {pid} : {len(remplacements)} lien(s)")

    print("\nÉCHANTILLON :")
    for pid, verdict, avant, apres in exemples:
        print(f"   [{verdict}] notule {pid}")
        print(f"      avant : {avant[:110]}")
        print(f"      après : {apres[:110]}")

    if not args.ecrire:
        print("\nSimulation. Relancez avec --ecrire pour écrire les correctifs.")
        return

    # --- écriture des correctifs -----------------------------------------
    CORRECTIONS.mkdir(parents=True, exist_ok=True)
    ecrits = 0

    for pid, remplacements in sorted(plan.items()):
        chemin = CORRECTIONS / f'{pid}.json'

        if chemin.is_file():
            correctif = json.loads(chemin.read_text(encoding='utf-8'))
        else:
            correctif = {'postId': pid,
                         'note': 'Liens web.archive.org réparés'}

        liste = correctif.setdefault('remplacements', [])
        deja = {r['chercher'] for r in liste}

        for avant, apres in remplacements.items():
            if avant in deja:
                continue
            liste.append({'chercher': avant, 'remplacer': apres,
                          'regex': False})

        chemin.write_text(
            json.dumps(correctif, ensure_ascii=False, indent=2) + '\n',
            encoding='utf-8')
        ecrits += 1

    print(f"\n{ecrits} correctif(s) écrit(s) dans {CORRECTIONS}")
    print("Relancez « npm run build », puis vérifiez avec :")
    print("   python scripts/diagnostic_webarchive.py")


if __name__ == '__main__':
    main()
