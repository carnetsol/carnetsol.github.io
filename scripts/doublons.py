#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Notules en double entre les deux collections.

    python scripts/doublons.py                 # rapport seul
    python scripts/doublons.py --ecrire        # retire les JSON en double

D'OÙ VIENNENT CES DOUBLONS
--------------------------
Une notule reprise de l'ancien site a d'abord été déposée en JSON dans
src/content/notules/, puis récrite en Markdown dans src/content/nouvelles/
— sans que la première version soit retirée. Le site lit les deux
collections et affiche donc deux fois le même texte, sous deux adresses
voisines.

CE QUE FAIT LE SCRIPT
---------------------
Il calcule l'adresse de CHAQUE notule des deux collections, exactement
comme le fait le site, puis signale :
  - deux notules à la même adresse ;
  - deux notules au même identifiant ;
  - deux notules de même titre et même date, même si les adresses
    diffèrent — c'est le cas le plus fréquent, un slug calculé
    différemment suffisant à les séparer.

Avec --ecrire, il retire la version JSON des doublons qui opposent
notules/ et nouvelles/. Le Markdown fait foi : c'est celui que vous
éditez. Un doublon entre deux JSON n'est jamais supprimé automatiquement,
il vous est seulement signalé.

Les fichiers retirés sont d'abord copiés dans .doublons-retires/.
"""

import argparse
import json
import re
import shutil
import sys
import unicodedata
from collections import defaultdict
from datetime import datetime
from pathlib import Path

for flux in (sys.stdout, sys.stderr):
    try:
        flux.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

NOTULES = Path('src/content/notules')
NOUVELLES = Path('src/content/nouvelles')
CORRECTIONS = Path('src/content/corrections')
CORBEILLE = Path('.doublons-retires')


def slugifier(valeur):
    """Reproduit slugifier() de src/lib/notules.ts."""
    s = unicodedata.normalize('NFD', valeur)
    s = ''.join(c for c in s if unicodedata.category(c) != 'Mn')
    s = s.lower().replace('|', '-')
    s = re.sub(r'[^\w\s-]', '', s).strip()
    return re.sub(r'[-\s]+', '-', s).strip('-') or 'notule'


def entete(texte):
    """
    Lecture minimale de l'en-tête YAML d'une notule Markdown.

    Volontairement rudimentaire : on n'a besoin que de cinq champs
    scalaires, et ajouter une dépendance YAML pour cela irait contre la
    règle « aucun paquet externe » du projet.
    """
    if not texte.startswith('---'):
        return {}
    fin = texte.find('\n---', 3)
    if fin == -1:
        return {}
    champs = {}
    for ligne in texte[3:fin].splitlines():
        if ':' not in ligne or ligne.strip().startswith('#'):
            continue
        cle, _, valeur = ligne.partition(':')
        valeur = valeur.strip().strip('"').strip("'")
        champs[cle.strip()] = valeur
    return champs


def lire_tout():
    """[(origine, chemin, postId, titre, date, url)] pour les deux collections."""
    entrees = []

    for f in sorted(NOTULES.glob('*.json')):
        try:
            d = json.loads(f.read_text(encoding='utf-8'))
        except (json.JSONDecodeError, OSError):
            print(f"   (illisible, ignoré : {f.name})")
            continue
        entrees.append(('json', f, int(d.get('postId', 0)),
                        d.get('titre', ''), str(d.get('date', ''))[:10],
                        d.get('url', '')))

    for f in sorted(list(NOUVELLES.glob('*.md')) + list(NOUVELLES.glob('*.mdx'))):
        e = entete(f.read_text(encoding='utf-8'))
        if not e.get('titre') or not e.get('date'):
            continue
        if str(e.get('brouillon', '')).lower() == 'true':
            continue
        date = str(e['date'])[:10]
        an, mois, jour = date.split('-')
        slug = e.get('slug') or slugifier(e['titre'])
        pid = int(e['postId']) if str(e.get('postId', '')).isdigit() else 0
        segment = f"{pid}-{slug}" if pid else slug
        entrees.append(('markdown', f, pid, e['titre'], date,
                        f"/css/{an}/{mois}/{jour}/{segment}/"))

    return entrees


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--ecrire', action='store_true')
    args = ap.parse_args()

    if not NOTULES.is_dir():
        print(f"ARRÊT — {NOTULES} introuvable. Lancez le script depuis la "
              "racine du projet.")
        sys.exit(1)

    entrees = lire_tout()
    json_n = sum(1 for e in entrees if e[0] == 'json')
    print(f"Notules JSON     : {json_n}")
    print(f"Notules Markdown : {len(entrees) - json_n}")

    # Trois clefs de rapprochement, de la plus stricte à la plus large.
    groupes = defaultdict(list)
    for e in entrees:
        origine, chemin, pid, titre, date, url = e
        groupes[('adresse', url)].append(e)
        if pid:
            groupes[('identifiant', pid)].append(e)
        groupes[('titre+date', slugifier(titre), date)].append(e)

    # Un même couple de notules peut se retrouver par plusieurs clefs :
    # on ne le signale qu'une fois, avec le motif le plus fort.
    vus, doublons = set(), []
    for clef, liste in groupes.items():
        if len(liste) < 2:
            continue
        empreinte = tuple(sorted(str(e[1]) for e in liste))
        if empreinte in vus:
            continue
        vus.add(empreinte)
        doublons.append((clef[0], liste))

    if not doublons:
        print("\nAucun doublon.")
        return

    print(f"\nDOUBLONS : {len(doublons)}\n")
    a_retirer = []
    for motif, liste in doublons:
        print(f"   [{motif} identique]")
        for origine, chemin, pid, titre, date, url in liste:
            print(f"      {origine:8}  {chemin}")
            print(f"                {date}  {titre[:52]}")
            print(f"                {url}")

        origines = {e[0] for e in liste}
        if origines == {'json', 'markdown'}:
            for e in liste:
                if e[0] == 'json':
                    a_retirer.append(e)
            print("      -> le Markdown fait foi, le JSON sera retiré")
        else:
            print("      -> deux fichiers de même nature : à trancher "
                  "vous-même, rien ne sera supprimé")
        print()

    if not a_retirer:
        return

    # Un correctif visant un identifiant qui disparaît ne sert plus à rien.
    orphelins = []
    for _, _, pid, _, _, _ in a_retirer:
        c = CORRECTIONS / f'{pid}.json'
        if pid and c.is_file():
            orphelins.append(c)

    print(f"À RETIRER : {len(a_retirer)} fichier(s) JSON")
    for _, chemin, _, _, _, _ in a_retirer:
        print(f"   {chemin}")
    if orphelins:
        print(f"\nCORRECTIFS DEVENUS SANS OBJET : {len(orphelins)}")
        for c in orphelins:
            print(f"   {c}")
        print("   (un correctif ne s'applique qu'aux notules JSON ; celui-ci")
        print("    ne toucherait plus rien une fois le JSON parti)")

    if not args.ecrire:
        print("\nRapport seul. Relancez avec --ecrire pour retirer ces fichiers.")
        return

    horodatage = datetime.now().strftime('%Y-%m-%d_%Hh%M')
    corbeille = CORBEILLE / horodatage
    corbeille.mkdir(parents=True, exist_ok=True)

    for _, chemin, _, _, _, _ in a_retirer:
        shutil.copy2(chemin, corbeille / chemin.name)
        chemin.unlink()
        print(f"retiré : {chemin}")
    for c in orphelins:
        shutil.copy2(c, corbeille / f'correction-{c.name}')
        c.unlink()
        print(f"retiré : {c}")

    print(f"\nCopies conservées dans {corbeille}")
    print("Relancez « npm run build » pour vérifier.")


if __name__ == '__main__':
    main()
