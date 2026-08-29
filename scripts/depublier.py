#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Dépublier ou republier une notule.

    python scripts/depublier.py 97004 --motif "Doublon contenant du brouillon"
    python scripts/depublier.py 97004 --republier
    python scripts/depublier.py --liste

POURQUOI UN CORRECTIF ET NON UNE SUPPRESSION
--------------------------------------------
Les fichiers de src/content/notules/ sont RÉGÉNÉRÉS à chaque migration
Dotclear. Supprimer 97004.json à la main marcherait jusqu'à la prochaine
exécution de migrate_dotclear.py, qui le recréerait sans un mot. La notule
reparaîtrait sur le site sans que personne ne s'en aperçoive.

On dépose donc un fichier dans src/content/corrections/, dossier qui n'est
jamais régénéré. Le site le lit à la compilation et écarte la notule du fil,
des archives, des chapitres, du flux RSS, de la chaîne des voisines, et ne
génère pas sa page. La notule d'origine reste intacte sur le disque : la
dépublication est réversible d'un mot.

STRUCTURE DU FICHIER PRODUIT
----------------------------
    {
      "postId": 97004,
      "note": "Doublon contenant du brouillon — dépubliée le 29/08/2026",
      "depublier": true
    }

Le même fichier peut porter d'autres corrections (titre, corpsHtml,
remplacements…) : le script complète ce qui existe au lieu de l'écraser.
"""

import argparse
import json
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


def indexer():
    """
    Index de TOUTES les notules, quel que soit le nom de leur fichier.

    Le nom du fichier n'est PAS l'identifiant. La migration Dotclear écrit
    bien 93042.json, mais l'import WordPress écrit
    « import-wp-20250416-ghedini-1892-1965-….json ». Chercher le fichier
    d'après le postId échouait donc sur tout ce qui vient des blogs
    compagnons. On lit désormais le contenu, seule source fiable.

    Renvoie une liste de (chemin, données).
    """
    fiches = []
    for f in sorted(NOTULES.glob('*.json')):
        try:
            fiches.append((f, json.loads(f.read_text(encoding='utf-8'))))
        except (json.JSONDecodeError, OSError):
            print(f"   (illisible, ignoré : {f.name})")
    return fiches


def trouver(fiches, cherche):
    """
    Retrouve une notule par identifiant, nom de fichier, slug ou adresse.
    On accepte les quatre parce qu'on ne sait jamais lequel on a sous la
    main : le postId vient du site, le nom de fichier de l'explorateur,
    le slug ou l'adresse du navigateur.
    """
    c = str(cherche).strip().removesuffix('.json').lower()

    if c.isdigit():
        for chemin, d in fiches:
            if int(d.get('postId', -1)) == int(c):
                return chemin, d

    for chemin, d in fiches:
        if chemin.stem.lower() == c:
            return chemin, d
    for chemin, d in fiches:
        if str(d.get('slug', '')).lower() == c:
            return chemin, d
    for chemin, d in fiches:
        if str(d.get('url', '')).lower().strip('/').endswith(c.strip('/')):
            return chemin, d

    # Rien d'exact : on propose les approchants plutôt que d'abandonner sec.
    approchants = [(chemin, d) for chemin, d in fiches
                   if c in chemin.stem.lower()
                   or c in str(d.get('slug', '')).lower()
                   or c in str(d.get('titre', '')).lower()]
    return None, approchants


def charger(chemin):
    if chemin.is_file():
        return json.loads(chemin.read_text(encoding='utf-8'))
    return None


def enregistrer(chemin, donnees):
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_text(json.dumps(donnees, ensure_ascii=False, indent=2) + '\n',
                      encoding='utf-8')


def lister():
    if not CORRECTIONS.is_dir():
        print("Aucun correctif.")
        return
    titres = {int(d['postId']): d.get('titre', '') for _, d in indexer()}
    trouvees = []
    for f in sorted(CORRECTIONS.glob('*.json')):
        d = charger(f)
        if d and d.get('depublier'):
            trouvees.append((d['postId'], d.get('note', ''),
                             titres.get(int(d['postId']), '')))

    if not trouvees:
        print("Aucune notule dépubliée.")
        return
    print(f"NOTULES DÉPUBLIÉES : {len(trouvees)}")
    for pid, note, titre in trouvees:
        print(f"   {pid}  {titre[:56]}")
        if note:
            print(f"          {note}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('quoi', nargs='?',
                    help="identifiant (93042), nom de fichier, slug ou "
                         "adresse de la notule")
    ap.add_argument('--motif', help="raison, inscrite dans le correctif")
    ap.add_argument('--republier', action='store_true',
                    help="annule une dépublication")
    ap.add_argument('--liste', action='store_true',
                    help="affiche les notules actuellement dépubliées")
    args = ap.parse_args()

    if not NOTULES.is_dir():
        print(f"ARRÊT — {NOTULES} introuvable. Lancez le script depuis la "
              "racine du projet.")
        sys.exit(1)

    if args.liste:
        lister()
        return

    if args.quoi is None:
        ap.print_help()
        print()
        lister()
        return

    chemin_source, source = trouver(indexer(), args.quoi)
    if chemin_source is None:
        print(f"ARRÊT — aucune notule ne correspond à « {args.quoi} ».")
        if source:
            print(f"        {len(source)} notule(s) approchante(s) :")
            for chemin, d in source[:10]:
                print(f"          {d.get('postId')}  {chemin.name}")
                print(f"                 {str(d.get('titre',''))[:64]}")
            print("        Relancez avec l'identifiant exact.")
        else:
            print("        Essayez l'identifiant, le nom du fichier, le slug "
                  "ou l'adresse.")
        sys.exit(1)

    postid = int(source['postId'])
    titre = source.get('titre', '')
    url = source.get('url', '')
    chemin = CORRECTIONS / f'{postid}.json'
    correctif = charger(chemin) or {'postId': postid}
    existait = chemin.is_file()

    quand = datetime.now().strftime('%d/%m/%Y')

    if args.republier:
        if not correctif.get('depublier'):
            print(f"La notule {postid} n'est pas dépubliée. Rien à faire.")
            return
        correctif['depublier'] = False
        correctif['note'] = f"Republiée le {quand}"

        # Si le correctif ne servait qu'à cela, on retire le fichier plutôt
        # que de laisser traîner une coquille vide.
        utiles = set(correctif) - {'postId', 'note', 'depublier'}
        if not utiles:
            chemin.unlink()
            print(f"Notule {postid} republiée. Correctif supprimé "
                  f"(il ne servait qu'à cela).")
        else:
            enregistrer(chemin, correctif)
            print(f"Notule {postid} republiée. Le correctif est conservé, "
                  f"il porte aussi : {', '.join(sorted(utiles))}.")
    else:
        correctif['depublier'] = True
        motif = args.motif or 'Dépubliée'
        correctif['note'] = f"{motif} — dépubliée le {quand}"
        enregistrer(chemin, correctif)
        print(f"Notule {postid} dépubliée.")

    print()
    print(f"   titre    : {titre}")
    print(f"   adresse  : {url}")
    print(f"   correctif: {chemin}" + ('' if existait else '   (créé)'))
    print()
    print("Relancez « npm run build » pour que le site en tienne compte.")
    print("Pensez à valider le correctif : git add " + str(chemin))


if __name__ == '__main__':
    main()
