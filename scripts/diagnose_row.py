#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Diagnostic : extrait du dump la portion brute concernant une notule donnée,
afin de comprendre pourquoi le découpage des champs se décale.

Usage :
    python diagnose_row.py dump.sql 1215
    python diagnose_row.py dump.sql 1215 --contexte 4000
"""

import argparse
import re
import sys


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dump")
    ap.add_argument("post_id")
    ap.add_argument("--contexte", type=int, default=2500,
                    help="nombre de caractères à afficher autour du repère")
    ap.add_argument("--sortie", default="extrait_brut.txt")
    args = ap.parse_args()

    with open(args.dump, "r", encoding="utf-8", errors="replace") as fh:
        texte = fh.read()

    # On cherche l'endroit du dump où commence l'INSERT de sursol_post,
    # puis le tuple qui commence par l'identifiant demandé.
    motif = re.compile(
        r"\(\s*'?" + re.escape(args.post_id) + r"'?\s*,\s*'DavidLeMarrec'",
    )

    trouve = list(motif.finditer(texte))
    if not trouve:
        print(f"Aucun tuple trouvé pour post_id = {args.post_id}", file=sys.stderr)
        print("Le décalage vient peut-être d'une ligne ANTÉRIEURE : dans ce cas "
              "l'identifiant n'apparaît pas en début de tuple.", file=sys.stderr)
        return

    for i, m in enumerate(trouve):
        debut = max(0, m.start() - 200)
        fin = min(len(texte), m.start() + args.contexte)
        extrait = texte[debut:fin]

        nom = args.sortie if len(trouve) == 1 else f"{i}_{args.sortie}"
        with open(nom, "w", encoding="utf-8") as fh:
            fh.write(extrait)

        print(f"\n=== occurrence {i + 1} sur {len(trouve)} "
              f"(position {m.start()}) -> {nom} ===")

        # Compte des quotes non échappées dans l'extrait : un nombre impair
        # trahit une chaîne mal refermée, cause classique de décalage.
        sans_echap = re.sub(r"\\.", "", extrait)
        print(f"apostrophes non échappées dans l'extrait : {sans_echap.count(chr(39))}")

        # Séquences suspectes
        for seq, desc in [
            ("\\\\'", "antislash suivi d'une quote"),
            ("''", "double apostrophe"),
            ("\\Z", "séquence \\Z"),
            ("\\0", "séquence \\0"),
        ]:
            n = extrait.count(seq)
            if n:
                print(f"  {desc} : {n} occurrence(s)")

        print("\n--- 600 premiers caractères ---")
        print(extrait[:600])


if __name__ == "__main__":
    main()
