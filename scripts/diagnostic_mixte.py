#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Diagnostic du CONTENU MIXTE.

    python scripts/diagnostic_mixte.py

NE MODIFIE RIEN.

POURQUOI CE SCRIPT
------------------
Le site est servi en https. Un navigateur moderne REFUSE de charger une
image, un son ou une vidéo demandés en http:// depuis une page https :
c'est la règle dite du « contenu mixte ». La ressource n'est pas affichée,
et rien ne l'annonce à l'écran — seule la console du navigateur le signale.

C'est la première explication à examiner quand des mp3 et des images
disparaissent sans motif apparent, alors que le fichier existe bel et bien.
Elle rend compte des deux symptômes d'un coup, et surtout du fait que le
mode lecture de Chrome affiche tout : ce mode récupère la page autrement et
n'applique pas le même blocage.

POUR VÉRIFIER EN DEUX MINUTES
-----------------------------
Ouvrez la notule fautive, appuyez sur F12, onglet « Console ». Un message
« Mixed Content: The page at … was loaded over HTTPS, but requested an
insecure element … » confirme le diagnostic sans discussion possible.

CE QUE FAIT LE SCRIPT
---------------------
Il relève toutes les ressources appelées en http:// dans le corps des
notules — src d'images, d'iframes, d'audio, de vidéo, et liens vers des
fichiers média — puis les regroupe par hôte, en indiquant lesquels
répondent aussi en https (auquel cas un simple remplacement suffit).
"""

import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

for flux in (sys.stdout, sys.stderr):
    try:
        flux.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

NOTULES = Path('src/content/notules')
RAPPORT = Path('rapport-mixte.tsv')

# src/href en http:// dans une balise de ressource, ou lien vers un média.
RESSOURCE = re.compile(
    r'<(img|iframe|audio|video|source|embed|object)\b[^>]*?'
    r'\b(?:src|data)\s*=\s*["\'](http://[^"\']+)["\']',
    re.I
)
MEDIA_LIE = re.compile(
    r'<a\b[^>]*?\bhref\s*=\s*["\'](http://[^"\']+\.'
    r'(?:mp3|mp4|ogg|oga|wav|flac|webm|m4a|jpe?g|png|gif|svg|pdf))["\']',
    re.I
)

CHAMPS = ['corpsHtml', 'chapoHtml', 'notesHtml']


def main():
    if not NOTULES.is_dir():
        print(f"ARRÊT — {NOTULES} introuvable. Lancez le script depuis la "
              "racine du projet.")
        sys.exit(1)

    lignes = []
    par_hote = Counter()
    par_type = Counter()
    notules_touchees = set()
    exemples_par_hote = defaultdict(list)

    fichiers = sorted(NOTULES.glob('*.json'))
    for f in fichiers:
        d = json.loads(f.read_text(encoding='utf-8'))
        for champ in CHAMPS:
            texte = d.get(champ) or ''

            for m in RESSOURCE.finditer(texte):
                balise, url = m.group(1).lower(), m.group(2)
                hote = re.match(r'http://([^/:?#]+)', url).group(1).lower()
                par_hote[hote] += 1
                par_type[balise] += 1
                notules_touchees.add(d['postId'])
                lignes.append((d['postId'], champ, balise, hote, url[:200]))
                if len(exemples_par_hote[hote]) < 2:
                    exemples_par_hote[hote].append((d['postId'], url))

            for m in MEDIA_LIE.finditer(texte):
                url = m.group(1)
                hote = re.match(r'http://([^/:?#]+)', url).group(1).lower()
                par_hote[hote] += 1
                par_type['lien'] += 1
                notules_touchees.add(d['postId'])
                lignes.append((d['postId'], champ, 'lien', hote, url[:200]))
                if len(exemples_par_hote[hote]) < 2:
                    exemples_par_hote[hote].append((d['postId'], url))

    print(f"Notules examinées : {len(fichiers)}")
    print(f"Ressources en http:// : {len(lignes)}")
    print(f"Notules touchées      : {len(notules_touchees)}")

    if not lignes:
        print("\nAucune ressource en clair. Le contenu mixte n'est pas la "
              "cause : cherchez ailleurs (chemin erroné, fichier absent).")
        return

    print("\nPAR TYPE DE BALISE :")
    for balise, n in par_type.most_common():
        print(f"   {n:>5}  {balise}")

    print("\nPAR HÔTE :")
    for hote, n in par_hote.most_common(20):
        print(f"   {n:>5}  {hote}")
        for pid, url in exemples_par_hote[hote][:1]:
            print(f"          notule {pid} : {url[:96]}")

    with RAPPORT.open('w', encoding='utf-8', newline='') as sortie:
        sortie.write('postId\tchamp\tbalise\thote\turl\n')
        for l in lignes:
            sortie.write('\t'.join(str(x) for x in l) + '\n')

    print(f"\nRapport complet : {RAPPORT}  ({len(lignes)} lignes)")
    print()
    print("SUITE POSSIBLE, selon ce que montre la liste :")
    print("  - hôte répondant en https  -> remplacer http:// par https://")
    print("  - hôte sans https (free.fr) -> rapatrier le fichier dans")
    print("                                 public/medias/ et pointer sur /medias/")
    print("Dites-moi ce que donne ce rapport et j'écris le correctif.")


if __name__ == '__main__':
    main()
