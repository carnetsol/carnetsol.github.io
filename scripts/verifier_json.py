#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Contrôle de validité des fichiers JSON de notules.

    python scripts/verifier_json.py            # contrôle seul
    python scripts/verifier_json.py --reparer  # corrige ce qui est sûr

POURQUOI
--------
Astro signale bien le fichier fautif, mais son message se réduit à une
position dans le fichier : « position 6970 (line 17 column 6525) ». Sur
une notule dont tout le corps tient sur une seule ligne, chercher la
colonne 6525 à la main n'est pas raisonnable. Ce script montre le texte
autour de la rupture, ce qui suffit presque toujours à comprendre.

LA FAUTE HABITUELLE
-------------------
Un GUILLEMET DROIT non échappé dans le corps de la notule :

    ... . Sur "chiudi", motif du dégoût ...

En JSON, le guillemet ferme la chaîne. Il doit s'écrire \\" — ou, dans du
HTML, &quot;. Le reste du fichier employait des entités, seul le dernier
bloc, collé plus tard, portait des guillemets bruts : c'est la signature
d'un ajout fait à la main après coup.

--reparer échappe les guillemets non protégés à l'intérieur des valeurs de
texte, puis vérifie que le fichier se relit. En cas d'échec, RIEN n'est
écrit : mieux vaut un fichier cassé qu'un fichier cassé autrement.
Une copie de l'original part dans .json-avant-reparation/.
"""

import argparse
import json
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

for flux in (sys.stdout, sys.stderr):
    try:
        flux.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

NOTULES = Path('src/content/notules')
CORRECTIONS = Path('src/content/corrections')
CORBEILLE = Path('.json-avant-reparation')

# Champs dont la valeur est du texte long, seuls susceptibles de contenir
# un guillemet oublié.
CHAMPS = ['corpsHtml', 'chapoHtml', 'notesHtml', 'extrait', 'titre']


def contexte(brut, position, avant=170, apres=60):
    debut = max(0, position - avant)
    return ('…' + brut[debut:position].replace('\n', ' ')
            + '  <<< ICI >>>  '
            + brut[position:position + apres].replace('\n', ' ') + '…')


def reparer(brut):
    """
    Échappe les guillemets non protégés à l'intérieur des champs de texte.
    Renvoie None si le résultat ne se relit pas.
    """
    sortie = brut
    for champ in CHAMPS:
        marque = f'"{champ}": "'
        if marque not in sortie:
            continue
        debut = sortie.index(marque) + len(marque)

        # La valeur s'arrête au guillemet suivi d'une virgule ou d'une
        # accolade en fin de ligne : c'est la seule borne fiable quand des
        # guillemets parasites traînent au milieu.
        m = re.compile(r'"\s*(,|\})\s*\n').search(sortie, debut)
        if not m:
            continue
        fin = m.start()

        valeur = sortie[debut:fin]
        corrigee = re.sub(r'(?<!\\)"', r'\\"', valeur)
        sortie = sortie[:debut] + corrigee + sortie[fin:]

    try:
        json.loads(sortie)
        return sortie
    except json.JSONDecodeError:
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--reparer', action='store_true')
    args = ap.parse_args()

    dossiers = [d for d in (NOTULES, CORRECTIONS) if d.is_dir()]
    if not dossiers:
        print("ARRÊT — src/content/notules introuvable. Lancez le script "
              "depuis la racine du projet.")
        sys.exit(1)

    fichiers = sorted(f for d in dossiers for f in d.glob('*.json'))
    casses = []

    for f in fichiers:
        brut = f.read_text(encoding='utf-8')
        try:
            json.loads(brut)
        except json.JSONDecodeError as e:
            casses.append((f, brut, e))

    print(f"Fichiers examinés : {len(fichiers)}")
    print(f"Fichiers illisibles : {len(casses)}")

    if not casses:
        print("\nTout se lit correctement.")
        return

    reparables = []
    for f, brut, e in casses:
        print(f"\n{'=' * 72}")
        print(f"{f}")
        print(f"   {e.msg} — ligne {e.lineno}, colonne {e.colno}")
        print(f"   {contexte(brut, e.pos)}")

        propose = reparer(brut)
        if propose:
            reparables.append((f, brut, propose))
            print("   -> réparable : guillemets à échapper")
        else:
            print("   -> NON réparable automatiquement, à corriger à la main")

    if not reparables:
        return

    print(f"\n{len(reparables)} fichier(s) réparable(s).")
    if not args.reparer:
        print("Relancez avec --reparer pour les corriger.")
        return

    horodatage = datetime.now().strftime('%Y-%m-%d_%Hh%M')
    corbeille = CORBEILLE / horodatage
    corbeille.mkdir(parents=True, exist_ok=True)

    for f, brut, propose in reparables:
        shutil.copy2(f, corbeille / f.name)
        # Réécrit à partir de l'objet relu : indentation et échappements
        # redeviennent uniformes dans tout le fichier.
        f.write_text(
            json.dumps(json.loads(propose), ensure_ascii=False, indent=1) + '\n',
            encoding='utf-8')
        print(f"réparé : {f}")

    print(f"\nOriginaux conservés dans {corbeille}")
    print("Relancez « npm run build ».")


if __name__ == '__main__':
    main()
