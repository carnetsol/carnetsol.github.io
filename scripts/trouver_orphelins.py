#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Distingue, dans public/medias (ou public/images), les fichiers RÉFÉRENCÉS
par au moins une notule de ceux qui n'apparaissent dans aucun lien —
probablement des documents personnels embarqués par erreur lors de la copie.

Ne déplace ni ne supprime rien : produit un rapport pour décider en connaissance
de cause, fichier par fichier si besoin.

Usage :
    python trouver_orphelins.py public\\medias src\\content\\notules
"""

import argparse
import json
import os
import re
import sys


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dossier_medias")
    ap.add_argument("dossier_notules")
    ap.add_argument("--sortie", default="fichiers-orphelins.txt")
    args = ap.parse_args()

    # Tous les noms de fichiers réellement liés depuis une notule ou une
    # correction, quel que soit le dossier de destination (/medias/, /images/…).
    # On relit le JSON *décodé* (pas le texte brut du fichier) : les guillemets
    # y sont échappés en \" et une simple recherche textuelle les manquerait.
    references = set()
    motif = re.compile(r'/(?:medias|images)/([^"\')\s>\\]+)')

    dossiers = [args.dossier_notules]
    correc = os.path.join(os.path.dirname(args.dossier_notules), "corrections")
    if os.path.isdir(correc):
        dossiers.append(correc)

    for dossier in dossiers:
        for nom in os.listdir(dossier):
            if not nom.endswith(".json"):
                continue
            with open(os.path.join(dossier, nom), encoding="utf-8") as fh:
                try:
                    d = json.load(fh)
                except json.JSONDecodeError:
                    continue
            texte = json.dumps(d, ensure_ascii=False)
            for m in motif.finditer(texte):
                references.add(os.path.basename(m.group(1)))

    print(f"{len(references)} noms de fichiers référencés par les notules",
          file=sys.stderr)

    fichiers = os.listdir(args.dossier_medias)
    orphelins, utilises = [], []
    for nom in fichiers:
        chemin = os.path.join(args.dossier_medias, nom)
        if not os.path.isfile(chemin):
            continue
        (utilises if nom in references else orphelins).append(nom)

    print(f"{len(utilises)} fichiers référencés, {len(orphelins)} orphelins",
          file=sys.stderr)

    par_ext = {}
    for nom in orphelins:
        ext = nom.rsplit(".", 1)[-1].lower() if "." in nom else "(sans extension)"
        par_ext.setdefault(ext, []).append(nom)

    lignes = [f"{len(orphelins)} fichiers non référencés par aucune notule :", ""]
    for ext, noms in sorted(par_ext.items(), key=lambda x: -len(x[1])):
        lignes.append(f"--- .{ext} ({len(noms)}) ---")
        for n in sorted(noms):
            lignes.append(f"  {n}")
        lignes.append("")

    with open(args.sortie, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lignes))

    print(f"\nRapport détaillé : {args.sortie}", file=sys.stderr)
    print("\nRépartition des orphelins par extension :", file=sys.stderr)
    for ext, noms in sorted(par_ext.items(), key=lambda x: -len(x[1])):
        print(f"  .{ext:8} {len(noms)}", file=sys.stderr)


if __name__ == "__main__":
    main()
