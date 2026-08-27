#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Diagnostic ciblé : découpe le tuple d'une notule champ par champ avec la même
logique que le script de migration, et affiche ce qui atterrit dans chaque
colonne. On voit ainsi immédiatement à partir d'où le décalage commence.

Usage :
    python diagnose_fields.py dump.sql 1215
"""

import argparse
import re
import sys

COLONNES = [
    "post_id", "user_id", "cat_id", "post_dt", "post_creadt", "post_upddt",
    "post_titre", "post_titre_url", "post_chapo", "post_chapo_wiki",
    "post_content", "post_content_wiki", "post_notes", "post_pub",
    "post_selected", "post_open_comment", "post_open_tb", "nb_comment",
    "nb_trackback", "nb_view", "post_lang",
]

UNESCAPE = {
    "0": "\0", "'": "'", '"': '"', "b": "\b", "n": "\n",
    "r": "\r", "t": "\t", "Z": "\x1a", "\\": "\\", "%": "\\%", "_": "\\_",
}


def lire_tuple(text, pos):
    """Découpe un seul tuple, en notant la position de départ de chaque champ."""
    champs = []
    n = len(text)
    assert text[pos] == "("
    pos += 1
    field = []
    is_string = False
    in_string = False
    depart = pos

    while pos < n:
        ch = text[pos]
        if in_string:
            if ch == "\\":
                nxt = text[pos + 1] if pos + 1 < n else ""
                field.append(UNESCAPE.get(nxt, nxt))
                pos += 2
                continue
            if ch == "'":
                if pos + 1 < n and text[pos + 1] == "'":
                    field.append("'")
                    pos += 2
                    continue
                in_string = False
                pos += 1
                continue
            field.append(ch)
            pos += 1
            continue

        if ch == "'":
            in_string = True
            is_string = True
            field = []
            pos += 1
            continue
        if ch == ",":
            champs.append(("".join(field), is_string, depart))
            field = []
            is_string = False
            pos += 1
            depart = pos
            continue
        if ch == ")":
            champs.append(("".join(field), is_string, depart))
            pos += 1
            break
        field.append(ch)
        pos += 1

    return champs, pos


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dump")
    ap.add_argument("post_id")
    args = ap.parse_args()

    with open(args.dump, "r", encoding="utf-8", errors="replace") as fh:
        texte = fh.read()

    motif = re.compile(r"\(\s*'?" + re.escape(args.post_id) + r"'?\s*,\s*'DavidLeMarrec'")
    m = motif.search(texte)
    if not m:
        print("Tuple introuvable.", file=sys.stderr)
        return

    champs, fin = lire_tuple(texte, m.start())

    print(f"Champs trouvés : {len(champs)} (attendu : {len(COLONNES)})\n")

    for i, (valeur, est_chaine, depart) in enumerate(champs):
        nom = COLONNES[i] if i < len(COLONNES) else f"!! SURNUMERAIRE {i}"
        type_ = "chaîne" if est_chaine else "brut"
        apercu = valeur[:70].replace("\n", "\\n").replace("\r", "\\r")
        marque = ""
        # Une colonne numérique qui reçoit du texte = décalage détecté
        if nom in ("post_pub", "post_selected", "post_open_comment",
                   "post_open_tb", "nb_comment", "nb_trackback", "nb_view",
                   "post_id", "cat_id"):
            try:
                int(valeur.strip())
            except ValueError:
                marque = "   <<<<<< DECALAGE ICI"
        print(f"[{i:2}] {nom:20} ({type_:6}, len={len(valeur):7}) {apercu!r}{marque}")

    print(f"\nFin du tuple à la position {fin}")

    # Affiche la zone autour du premier champ décalé, pour voir la cause
    for i, (valeur, _, depart) in enumerate(champs):
        nom = COLONNES[i] if i < len(COLONNES) else None
        if nom in ("post_pub", "nb_comment") :
            try:
                int(valeur.strip())
            except ValueError:
                debut_zone = max(0, depart - 400)
                print("\n=== texte brut du dump juste avant le décalage ===")
                print(texte[debut_zone:depart + 100])
                with open("zone_decalage.txt", "w", encoding="utf-8") as fh:
                    fh.write(texte[max(0, depart - 3000):depart + 500])
                print("\n(zone élargie écrite dans zone_decalage.txt)")
                break


if __name__ == "__main__":
    main()
