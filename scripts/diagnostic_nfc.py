#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Diagnostic des textes en forme Unicode DÉCOMPOSÉE.

    python scripts/diagnostic_nfc.py

NE MODIFIE RIEN. Le site normalise déjà tout à la lecture — ce script sert
seulement à mesurer l'ampleur du phénomène et à repérer les notules
concernées, au cas où l'une d'elles demanderait un examen à la main.

DE QUOI S'AGIT-IL
-----------------
Une même chaîne s'écrit de deux façons en Unicode. « ὲ » peut être un seul
caractère (U+1F72), ou deux : un epsilon suivi d'un accent grave combinant
(U+03B5 U+0300). Les deux sont valides. Mais beaucoup de polices placent
mal l'accent combinant, qui apparaît alors décalé à côté de la lettre :
« Μηδὲ`ν » au lieu de « Μηδὲν ». Ce n'est pas une coquille du texte, c'est
un défaut de rendu.

Le grec ancien polytonique est le cas le plus voyant, parce qu'il empile
jusqu'à trois signes sur une voyelle. Le français accentué est concerné de
la même façon, en plus discret : « é » décomposé s'affiche généralement
bien, mais pas toujours, et il casse la recherche plein texte — chercher
« Pelléas » ne trouve pas un « Pelléas » décomposé.
"""

import json
import sys
import unicodedata
from collections import Counter
from pathlib import Path

for flux in (sys.stdout, sys.stderr):
    try:
        flux.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

NOTULES = Path('src/content/notules')
CHAMPS = ['titre', 'chapoHtml', 'corpsHtml', 'notesHtml', 'extrait']


def decompose(texte):
    """Le texte contient-il des signes combinants ?"""
    return any(0x0300 <= ord(c) <= 0x036F or 0x1AB0 <= ord(c) <= 0x1AFF
               for c in texte or '')


def main():
    if not NOTULES.is_dir():
        print(f"ARRÊT — {NOTULES} introuvable. Lancez le script depuis la "
              "racine du projet.")
        sys.exit(1)

    touchees = []
    par_champ = Counter()
    signes = Counter()
    total = 0

    for f in sorted(NOTULES.glob('*.json')):
        try:
            d = json.loads(f.read_text(encoding='utf-8'))
        except (json.JSONDecodeError, OSError):
            continue
        total += 1

        champs_touches = []
        for champ in CHAMPS:
            texte = d.get(champ) or ''
            if not decompose(texte):
                continue
            champs_touches.append(champ)
            par_champ[champ] += 1
            for c in texte:
                if 0x0300 <= ord(c) <= 0x036F:
                    signes[c] += 1

        if champs_touches:
            touchees.append((d.get('postId'), d.get('titre', ''),
                             champs_touches))

    print(f"Notules examinées : {total}")
    print(f"Notules contenant du texte décomposé : {len(touchees)}")

    if not touchees:
        print("\nTout est déjà en forme composée. Rien à signaler.")
        return

    print("\nPAR CHAMP :")
    for champ, n in par_champ.most_common():
        print(f"   {n:>5}  {champ}")

    print("\nSIGNES COMBINANTS RENCONTRÉS :")
    for c, n in signes.most_common(10):
        print(f"   {n:>5}  U+{ord(c):04X}  "
              f"{unicodedata.name(c, 'sans nom')}")

    print(f"\nNOTULES CONCERNÉES ({len(touchees)}) :")
    for pid, titre, champs in touchees[:30]:
        print(f"   {pid:>7}  [{', '.join(champs)}]")
        print(f"            {titre[:66]}")
    if len(touchees) > 30:
        print(f"   … et {len(touchees) - 30} autres.")

    print("\nAucune action requise : src/content.config.ts normalise ces")
    print("textes à la lecture, à chaque compilation. Cette liste sert")
    print("seulement à savoir ce qui était concerné.")


if __name__ == '__main__':
    main()
