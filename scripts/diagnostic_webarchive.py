#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Diagnostic des liens vers web.archive.org dans les notules.

    python scripts/diagnostic_webarchive.py

NE MODIFIE RIEN. Le script parcourt src/content/notules/*.json, relève
chaque adresse web.archive.org, en extrait l'adresse d'origine, et tente
de la faire correspondre à une notule du site.

Trois issues possibles pour chaque lien :
  APPARIÉ SLUG   l'adresse d'origine porte un slug qui existe sur le site
  APPARIÉ ID     le slug ne correspond à rien, mais l'identifiant oui
  ORPHELIN       ni l'un ni l'autre

L'appariement par SLUG est prioritaire, parce que les identifiants ont pu
changer entre l'ancien site et le nouveau, tandis que le slug est dérivé
du titre et bouge beaucoup moins.

Le rapport détaillé part dans rapport-webarchive.tsv (ouvrable au tableur).
"""

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

DOSSIER = Path('src/content/notules')
RAPPORT = Path('rapport-webarchive.tsv')

# https://web.archive.org/web/20230415123456/http://exemple.fr/page
#                            ^ horodatage    ^ adresse d'origine
# L'horodatage peut porter un suffixe (id_, im_, cs_…) selon le type de
# ressource archivée ; d'où le \w* après les chiffres.
WAYBACK = re.compile(
    r'https?://(?:web\.)?archive\.org/web/(\d{4,14})(\w*)/(https?[^\s"\'<>)]+)',
    re.I
)

# Adresse d'une notule, dans ses deux écritures historiques :
#   .../css/index.php?2013/04/04/2230-slug      (Dotclear, chaîne de requête)
#   .../css/2013/04/04/2230-slug                (réécrite)
NOTULE = re.compile(
    r'/css/(?:index\.php\?)?(\d{4})/(\d{2})/(\d{2})/(\d+)(?:-([^/?#&]*))?',
    re.I
)

CHAMPS = ['corpsHtml', 'chapoHtml', 'notesHtml', 'extrait']


def normaliser(slug):
    """Compare les slugs sans accent, sans casse, sans ponctuation."""
    s = unquote(slug or '')
    s = unicodedata.normalize('NFD', s)
    s = ''.join(c for c in s if unicodedata.category(c) != 'Mn')
    return re.sub(r'[^a-z0-9]+', '-', s.lower()).strip('-')


def main():
    if not DOSSIER.is_dir():
        print(f"ARRÊT — {DOSSIER} introuvable. Lancez le script depuis la "
              "racine du projet.")
        sys.exit(1)

    fichiers = sorted(DOSSIER.glob('*.json'))
    print(f"Notules examinées : {len(fichiers)}")

    # --- Index du site : slug -> url, identifiant -> url ------------------
    par_slug, par_id, notules = {}, {}, []
    for f in fichiers:
        d = json.loads(f.read_text(encoding='utf-8'))
        notules.append((f, d))
        par_slug[normaliser(d.get('slug', ''))] = d['url']
        par_id[int(d['postId'])] = d['url']

    print(f"Slugs indexés     : {len(par_slug)}")
    print()

    # --- Relevé ----------------------------------------------------------
    lignes = []
    stats = Counter()
    hotes = Counter()

    for f, d in notules:
        for champ in CHAMPS:
            texte = d.get(champ) or ''
            for m in WAYBACK.finditer(texte):
                origine = m.group(3)
                hote = re.match(r'https?://([^/:?#]+)', origine)
                hotes[hote.group(1).lower() if hote else '?'] += 1

                n = NOTULE.search(origine)
                if not n:
                    stats['EXTERNE'] += 1
                    lignes.append((d['postId'], champ, 'EXTERNE', '',
                                   origine[:200], ''))
                    continue

                identifiant = int(n.group(4))
                slug = normaliser(n.group(5) or '')

                cible = par_slug.get(slug) if slug else None
                if cible:
                    verdict = 'APPARIE_SLUG'
                else:
                    cible = par_id.get(identifiant)
                    verdict = 'APPARIE_ID' if cible else 'ORPHELIN'

                stats[verdict] += 1
                lignes.append((d['postId'], champ, verdict, identifiant,
                               origine[:200], cible or ''))

    total = sum(stats.values())
    print(f"LIENS WEBARCHIVE TROUVÉS : {total}")
    if not total:
        print("Rien à réparer.")
        return

    for verdict in ('APPARIE_SLUG', 'APPARIE_ID', 'ORPHELIN', 'EXTERNE'):
        n = stats[verdict]
        if n:
            print(f"   {verdict:<14} {n:>5}   ({100 * n / total:.1f} %)")

    print("\nHÔTES ARCHIVÉS (les 12 premiers) :")
    for hote, n in hotes.most_common(12):
        print(f"   {n:>5}  {hote}")

    print("\nORPHELINS — 20 premiers, ce sont eux qui décideront de la suite :")
    orphelins = [l for l in lignes if l[2] == 'ORPHELIN']
    for l in orphelins[:20]:
        print(f"   notule {l[0]}  id={l[3]}  {l[4][:110]}")
    if len(orphelins) > 20:
        print(f"   … et {len(orphelins) - 20} autres, voir le fichier.")

    with RAPPORT.open('w', encoding='utf-8', newline='') as sortie:
        sortie.write('postId\tchamp\tverdict\tidentifiant\torigine\tcible\n')
        for l in lignes:
            sortie.write('\t'.join(str(x) for x in l) + '\n')

    print(f"\nRapport complet : {RAPPORT}  ({len(lignes)} lignes)")
    print("Envoyez-le-moi, j'écris ensuite le script de réparation.")


if __name__ == '__main__':
    main()
