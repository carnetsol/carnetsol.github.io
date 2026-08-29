#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Remet src/content/categories.json en état après une migration.

DEUX TÂCHES, à faire ensemble :
  1. rétablir l'ordre voulu (le dump réimpose celui de Dotclear) ;
  2. rendre les catégories que le dump ne connaît pas.

Pourquoi la seconde : migrate_dotclear.py RÉÉCRIT categories.json de fond en
comble, à partir du seul dump SQL. Tout ce qui n'y figure pas disparaît —
« Les vidéos de Carnets sur sol », ajoutée par l'import YouTube, et toute
catégorie propre aux blogs compagnons. Les notules, elles, survivent (le
script n'efface rien dans notules/), si bien qu'elles se retrouvent
rattachées à une catégorie inexistante : plus de page de chapitre, plus de
lien, et aucun message d'erreur.

Le script relit donc les catégories réellement citées par les notules et
recrée celles qui manquent.

Ordonne src/content/categories.json selon l'ordre voulu.

    python scripts/ordonner_categories.py                # simulation
    python scripts/ordonner_categories.py --ecrire       # applique

L'ordre est inscrit dans ORDRE ci-dessous. Une ligne contenant un simple
tiret marque un SÉPARATEUR : la page des catégories tracera un filet à cet
endroit. Les catégories absentes de la liste sont rejetées en fin de page,
par ordre alphabétique, dans un troisième bloc à elles.

Les numéros attribués au champ « ordre » suivent cette convention :
      0 …  999   bloc 1 (avant le séparateur)
   1000 … 1999   bloc 2 (après le séparateur)
   2000 … 2999   catégories non listées, alphabétiques
La page insère un filet chaque fois que le millier change : la structure
tient donc dans le seul fichier de données, sans rien coder en dur dans
le gabarit.

Le fichier d'origine est sauvegardé en categories.json.avant-<horodatage>.
"""

import argparse
import json
import locale
import re
import shutil
import sys
import unicodedata
from datetime import datetime
from pathlib import Path

for flux in (sys.stdout, sys.stderr):
    try:
        flux.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

ORDRE = """
La musique en Ukraine
Une décennie, un disque
1 jour, 1 opéra
La Bible par la musique
Déchiffrages & Improvisations
Saison 2025-2026
Saison 2026-2027
Intendance
Langue
Littérature
D'Oehlenschläger à Ibsen
Vampires d'été : Byron, Marschner, Stoker
Zorro et ses mythes
Citations passantes
Poésie, lied & lieder
Découverte du lied
Clara Wieck-Schumann
Alma Schindler-Mahler
Projet lied français
Mélodie française
Découverte de la mélodie
Faust
Via Crucis de Liszt
Goblin Awards, Sélection Lutins & Putti d'incarnat
Les plus beaux récitatifs
Premiers opéras
Baroque français et tragédie lyrique
Opéra baroque européen
Opéra seria
Opéras de l'ère classique
Andromaque de Grétry (1780)
Tirso, Molière, Beaumarchais, Da Ponte et Mozart
Opéra-comique (et opérette)
Opéra romantique allemand
Le Vampire de Marschner
L'horrible Richard Wagner
Opéra romantique et vériste italien
Opéra romantique et postromantique européen
Opéra romantique français et Grand Opéra
Hamlet d'Ambroise Thomas
Sigurd d'Ernest Reyer
Opéras français d'après le romantisme
Wagnérismes français
Autour de Pelléas et Mélisande
Les plus beaux décadents
Vienne décade, et Richard Strauss
Die Gezeichneten (les stigmatisés)
Opéra russe
Opéras des écoles du vingtième siècle
Comédie musicale
Chansons & Rondels
Kunqu & théâtre chanté chinois
Théâtre (musical) grec
Musique de scène
-
Oeuvres
Genres
Livrets
Portraits
Pédagogique
Glottologie
Discographies
Disques et représentations
Saison 2009-2010
Saison 2010-2011
Saison 2011-2012
Saison 2012-2013
Saison 2013-2014
Saison 2014-2015
Saison 2015-2016
Saison 2016-2017
Saison 2017-2018
Saison 2018-2019
Saison 2019-2020
Saison 2020-2021
Saison 2021-2022
Saison 2022-2023
Saison 2023-2024
Petits marteaux
Quatuor à cordes
Domaine chambriste
Domaine symphonique
Bons tuyaux et grandes orgues
Domaine religieux et ecclésiastique
Opéra, opéras
Ballet et gargouillades
Musicontempo
Carnet d'écoutes
Le disque du jour
Le disque de la semaine
Son & Lumière du jour
Lutin Chamber Orchestra
Musique, domaine public
Discourir
Architecture
Pictural
Au théâtre
Théâtre filmé (et autres cinémas)
Tribune libre
Les astuces de Tonton David
En passant - brèves et jeux
H.S.
Vaste monde et gentils
A l'index
Musique ancienne
Musique baroque
Musique de la période classique
Musiques du vingtième siècle
"""


NOTULES = Path('src/content/notules')


def categories_citees():
    """
    Catégories réellement employées par les notules, telles qu'elles y sont
    inscrites. C'est la source de vérité : une catégorie citée par une
    notule doit exister, sans quoi la notule devient inaccessible par ce
    chemin.
    """
    vues = {}
    if not NOTULES.is_dir():
        return vues
    for f in NOTULES.glob('*.json'):
        try:
            d = json.loads(f.read_text(encoding='utf-8'))
        except (json.JSONDecodeError, OSError):
            continue
        for c in d.get('categories') or []:
            slug = c.get('slug')
            if slug and slug not in vues:
                vues[slug] = c.get('nom') or slug
    return vues


def cle(nom):
    """
    Clef d'appariement insensible aux accents, à la casse et à la
    ponctuation. « Opéra-comique (et opérette) » et « Opera comique et
    operette » se rejoignent donc, ce qui évite de faire échouer
    l'appariement sur une esperluette ou un trait d'union.
    """
    s = unicodedata.normalize('NFD', nom)
    s = ''.join(c for c in s if unicodedata.category(c) != 'Mn')
    return re.sub(r'[^a-z0-9]+', '', s.lower())


def tri_francais(nom):
    try:
        locale.setlocale(locale.LC_COLLATE, 'fr_FR.UTF-8')
        return locale.strxfrm(nom)
    except locale.Error:
        # Repli si la locale française n'est pas installée (fréquent sous
        # Windows) : on trie sur la forme sans accents, ce qui donne le
        # même résultat dans l'immense majorité des cas.
        return cle(nom)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--fichier', default='src/content/categories.json')
    ap.add_argument('--ecrire', action='store_true',
                    help="applique les changements (sinon simple simulation)")
    args = ap.parse_args()

    chemin = Path(args.fichier)
    if not chemin.is_file():
        print(f"ARRÊT — {chemin} introuvable.")
        print("Lancez le script depuis la racine du projet.")
        sys.exit(1)

    cats = json.loads(chemin.read_text(encoding='utf-8'))

    # --- rendre ce que la migration a effacé ------------------------------
    connus = {c['slug'] for c in cats}
    rendues = []
    for slug, nom in sorted(categories_citees().items()):
        if slug in connus:
            continue
        cats.append({
            'id': max([0] + [int(c['id']) for c in cats]) + 1,
            'nom': nom,
            'description': '',
            'slug': slug,
            'ordre': 2000,
        })
        rendues.append(nom)

    index = {}
    for c in cats:
        index.setdefault(cle(c['nom']), []).append(c)

    lignes = [l.strip() for l in ORDRE.strip().splitlines() if l.strip()]

    rang = {}          # clef -> numéro d'ordre
    introuvables = []
    bloc, position = 0, 0

    for ligne in lignes:
        if ligne == '-':
            bloc += 1
            position = 0
            continue
        k = cle(ligne)
        if k not in index:
            introuvables.append(ligne)
            continue
        rang[k] = bloc * 1000 + position
        position += 1

    # Ce qui n'est pas dans la liste : bloc 2000, alphabétique.
    # « _ » est la pseudo-catégorie de Dotclear, jamais affichée.
    restantes = sorted(
        (c for c in cats if cle(c['nom']) not in rang and c['nom'] != '_'),
        key=lambda c: tri_francais(c['nom'])
    )
    for i, c in enumerate(restantes):
        rang[cle(c['nom'])] = 2000 + i

    # Application
    changements = []
    for c in cats:
        k = cle(c['nom'])
        nouveau = rang.get(k, 9999)
        if c.get('ordre') != nouveau:
            changements.append((c['nom'], c.get('ordre'), nouveau))
        c['ordre'] = nouveau

    cats.sort(key=lambda c: (c['ordre'], tri_francais(c['nom'])))

    # Rapport
    if rendues:
        print("CATÉGORIES RENDUES (citées par des notules, absentes du "
              "fichier) :")
        for nom in rendues:
            print("   +", nom)
        print()

    print(f"catégories dans le fichier : {len(cats)}")
    print(f"noms listés appariés       : {len(lignes) - 1 - len(introuvables)}")
    print(f"rejetées en fin de page    : {len(restantes)}")
    print(f"champs « ordre » modifiés   : {len(changements)}")

    if introuvables:
        print("\nNOMS DE VOTRE LISTE SANS CATÉGORIE CORRESPONDANTE :")
        for n in introuvables:
            print("   -", n)

    if restantes:
        print("\nNON LISTÉES, placées en fin de page par ordre alphabétique :")
        for c in restantes:
            print("   -", c['nom'])

    print("\nAPERÇU DE L'ORDRE OBTENU :")
    precedent = None
    for c in cats:
        millier = c['ordre'] // 1000
        if precedent is not None and millier != precedent:
            print("   " + "-" * 40 + "  (filet)")
        precedent = millier
        print(f"   {c['ordre']:>5}  {c['nom']}")

    if not args.ecrire:
        print("\nSimulation. Relancez avec --ecrire pour appliquer.")
        return

    horodatage = datetime.now().strftime('%Y-%m-%d_%Hh%M')
    sauvegarde = chemin.with_suffix(f'.json.avant-{horodatage}')
    shutil.copy2(chemin, sauvegarde)

    chemin.write_text(
        json.dumps(cats, ensure_ascii=False, indent=2) + '\n',
        encoding='utf-8'
    )
    print(f"\nÉcrit.   Sauvegarde : {sauvegarde}")
    print("Relancez « npm run build » pour vérifier.")


if __name__ == '__main__':
    main()
