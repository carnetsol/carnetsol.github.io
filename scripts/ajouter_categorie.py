# -*- coding: utf-8 -*-
"""
Ajoute une catégorie à des notules DÉJÀ écrites, sans les réimporter.

Sert après coup, quand on s'aperçoit qu'un lot importé mérite une catégorie
thématique en plus de sa catégorie de provenance.

La sélection se fait par catégorie déjà portée, éventuellement bornée dans le
temps (pour les saisons musicales).

Exemples :
    python scripts\\ajouter_categorie.py --si carnets-sur-sol-disques ^
        --ajouter "Disques et représentations"

    python scripts\\ajouter_categorie.py --si carnets-sur-sol-concerts ^
        --ajouter "Saison 2024-2025" --du 2024-09-01 --au 2025-08-31

Sans --ecrire, rien n'est modifié : le script se contente d'annoncer.
Zéro dépendance externe.
"""

import argparse
import json
import os
import re
import sys
import unicodedata


def slugifier(valeur):
    valeur = unicodedata.normalize("NFD", valeur or "")
    valeur = "".join(c for c in valeur if unicodedata.category(c) != "Mn")
    valeur = re.sub(r"[^a-z0-9]+", "-", valeur.lower())
    return re.sub(r"-{2,}", "-", valeur).strip("-")


def resoudre_categorie(racine, nom, ecrire):
    """Retrouve le slug réel de la catégorie, ou la crée si elle manque.

    Le slug d'une catégorie Dotclear ne se déduit pas de son nom :
    « Disques et représentations » a pour slug « Representations », et
    « Vaste monde et gentils » a pour slug « Revue-de-toile ». On compare
    donc sur le nom, jamais sur le slug supposé.
    """
    chemin = os.path.join(racine, "src", "content", "categories.json")
    with open(chemin, encoding="utf-8") as fh:
        categories = json.load(fh)

    cible = slugifier(nom)
    for cat in categories:
        if slugifier(cat.get("nom", "")) == cible:
            return {"nom": cat["nom"], "slug": cat["slug"]}, False

    def entier(v, d=0):
        try:
            return int(v)
        except (TypeError, ValueError):
            return d

    neuve = {
        "id": max([entier(c.get("id")) for c in categories] or [0]) + 1,
        "nom": nom,
        "description": "",
        "slug": cible,
        "ordre": max([entier(c.get("ordre")) for c in categories] or [0]) + 1,
    }
    categories.append(neuve)
    if ecrire:
        with open(chemin, "w", encoding="utf-8") as fh:
            json.dump(categories, fh, ensure_ascii=False, indent=1)
    return {"nom": nom, "slug": cible}, True


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--racine", default=".")
    ap.add_argument("--si", metavar="SLUG",
                    help="ne traite que les notules portant déjà cette "
                         "catégorie (son slug)")
    ap.add_argument("--postid", metavar="N,N,N",
                    help="ne traite que ces identifiants de notules ; "
                         "sert au classement fin, notule par notule")
    ap.add_argument("--ajouter", required=True, metavar="NOM",
                    help="nom de la catégorie à ajouter")
    ap.add_argument("--du", metavar="AAAA-MM-JJ", help="date minimale incluse")
    ap.add_argument("--au", metavar="AAAA-MM-JJ", help="date maximale incluse")
    ap.add_argument("--ecrire", action="store_true")
    args = ap.parse_args()

    if not args.si and not args.postid:
        sys.exit("Indiquez au moins --si ou --postid.")

    vises = set()
    if args.postid:
        for n in args.postid.split(","):
            n = n.strip()
            if n:
                try:
                    vises.add(int(n))
                except ValueError:
                    sys.exit("--postid : « %s » n'est pas un nombre." % n)

    dossier = os.path.join(args.racine, "src", "content", "notules")
    if not os.path.isdir(dossier):
        sys.exit("Dossier introuvable : %s\n"
                 "Lancez le script depuis la racine du projet." % dossier)

    cat, creee = resoudre_categorie(args.racine, args.ajouter, args.ecrire)
    if creee:
        print("  catégorie %s : « %s » -> %s"
              % ("CRÉÉE" if args.ecrire else "À CRÉER", cat["nom"], cat["slug"]))
    else:
        print("  catégorie trouvée : « %s » -> %s" % (cat["nom"], cat["slug"]))

    touchees, deja, hors_bornes = [], 0, 0
    trouves = set()

    for nom_fichier in sorted(os.listdir(dossier)):
        if not nom_fichier.endswith(".json"):
            continue
        chemin = os.path.join(dossier, nom_fichier)
        try:
            with open(chemin, encoding="utf-8") as fh:
                notule = json.load(fh)
        except Exception as err:
            print("  !! %s illisible (%s)" % (nom_fichier, err), file=sys.stderr)
            continue

        slugs = [c.get("slug") for c in notule.get("categories", [])]
        if args.si and args.si not in slugs:
            continue
        if vises:
            try:
                if int(notule.get("postId", -1)) not in vises:
                    continue
            except (TypeError, ValueError):
                continue

        jour = str(notule.get("date", ""))[:10]
        if (args.du and jour < args.du) or (args.au and jour > args.au):
            hors_bornes += 1
            continue

        trouves.add(int(notule.get("postId", -1)))

        if cat["slug"] in slugs:
            deja += 1
            continue

        notule["categories"].append(dict(cat))
        touchees.append("  [%s] %s — %s"
                        % (notule.get("postId"), jour,
                           str(notule.get("titre", ""))[:58]))
        if args.ecrire:
            with open(chemin, "w", encoding="utf-8") as fh:
                json.dump(notule, fh, ensure_ascii=False, indent=1)

    critere = []
    if args.si:
        critere.append("portant « %s »" % args.si)
    if vises:
        critere.append("d'identifiant %s"
                       % ", ".join(str(n) for n in sorted(vises)))
    if args.du or args.au:
        critere.append("entre %s et %s" % (args.du or "…", args.au or "…"))
    print("\nSélection : notules " + " et ".join(critere))
    if vises:
        introuvables = vises - trouves
        if introuvables:
            print("!! aucune notule d'identifiant %s"
                  % ", ".join(str(n) for n in sorted(introuvables)))
    print("À modifier : %d" % len(touchees))
    if deja:
        print("Déjà classées ainsi : %d (inchangées)" % deja)
    if hors_bornes:
        print("Hors bornes de date : %d (inchangées)" % hors_bornes)
    print()
    print("\n".join(touchees))

    if args.ecrire:
        print("\n%d notules mises à jour." % len(touchees))
    else:
        print("\n>>> SIMULATION — rien n'a été modifié. "
              "Relancez avec --ecrire pour appliquer.")


if __name__ == "__main__":
    main()
