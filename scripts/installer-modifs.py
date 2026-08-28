#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Installation des modifications de Carnets sur sol.

    python installer-modifs.py

Le script ne fait rien avant d'avoir vérifié trois choses :
  1. qu'il a bien trouvé le zip téléchargé ;
  2. qu'il pointe bien sur votre projet Astro (et pas sur un dossier voisin) ;
  3. que vous avez lu la liste de ce qu'il va remplacer et dit oui.

Tout fichier écrasé est d'abord copié dans .sauvegardes/<horodatage>/.
Après copie, il lance une compilation d'essai : si elle échoue, il remet
lui-même l'état d'origine et vous n'avez rien à faire.

Pour revenir en arrière à la main, à n'importe quel moment :

    python installer-modifs.py --annuler .sauvegardes/2026-08-28_18h30

Options :
    --zip CHEMIN      indiquer le zip si le script ne le trouve pas
    --projet CHEMIN   indiquer le projet si le script ne le trouve pas
    --sans-build      ne pas compiler après la copie (déconseillé)
    --annuler DOSSIER restaurer une sauvegarde
"""

import argparse
import filecmp
import hashlib
import os
import shutil
import subprocess
import sys
import zipfile
from datetime import datetime
from pathlib import Path

# Sous Windows, la console n'est pas toujours en UTF-8 : sans cela, le
# premier « é » affiché ferait planter le script.
for flux in (sys.stdout, sys.stderr):
    try:
        flux.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

NOM_ZIP = 'carnetsol-modifs.zip'

# Ce que le projet doit contenir pour être reconnu. Si l'un manque,
# on n'est pas dans Carnets sur sol et le script s'arrête.
EMPREINTES = [
    'astro.config.mjs',
    'package.json',
    'src/pages/css/[...permalien].astro',
    'src/content.config.ts',
]


def dire(message=''):
    print(message)


def abandonner(message):
    dire()
    dire('ARRÊT — ' + message)
    dire('Rien n\'a été modifié.')
    sys.exit(1)


def somme(chemin: Path) -> str:
    return hashlib.sha256(chemin.read_bytes()).hexdigest()


# --------------------------------------------------------------------------
# Localisation du zip et du projet
# --------------------------------------------------------------------------

def trouver_zip(indique):
    if indique:
        p = Path(indique).expanduser()
        if not p.is_file():
            abandonner(f'le zip indiqué est introuvable : {p}')
        return p

    candidats = []
    for dossier in [Path.cwd(),
                    Path.home() / 'Downloads',
                    Path.home() / 'Téléchargements',
                    Path.home() / 'Desktop',
                    Path.home() / 'Bureau']:
        try:
            candidats += sorted(dossier.glob('carnetsol-modifs*.zip'))
        except OSError:
            pass

    if not candidats:
        abandonner('zip introuvable. Relancez avec --zip "C:\\chemin\\vers\\'
                   + NOM_ZIP + '"')

    # Le plus récent : si vous avez téléchargé deux fois, c'est le bon.
    candidats.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    if len(candidats) > 1:
        dire('Plusieurs zips trouvés, le plus récent est retenu :')
        for c in candidats:
            date = datetime.fromtimestamp(c.stat().st_mtime).strftime('%d/%m/%Y %Hh%M')
            dire(f'   {"→" if c == candidats[0] else " "} {c}  ({date})')
        dire()
    return candidats[0]


def trouver_projet(indique):
    if indique:
        depart = [Path(indique).expanduser()]
    else:
        # Le dossier du script, le dossier courant, puis les parents.
        # Le script marche donc lancé depuis la racine, depuis src/, depuis scripts/,
        # ou depuis n'importe quel dossier enfant.
        depart = [Path(__file__).parent, Path.cwd()] + list(Path.cwd().parents)

    for p in depart:
        if all((p / e).exists() for e in EMPREINTES):
            return p.resolve()

    dire('Le dossier ne ressemble pas au projet Carnets sur sol.')
    dire('Il doit contenir tout ceci :')
    for e in EMPREINTES:
        etat = 'présent' if (depart[0] / e).exists() else 'MANQUANT'
        dire(f'   [{etat:8}] {e}')
    abandonner('relancez depuis la racine du projet, ou avec '
               '--projet "C:\\chemin\\vers\\carnetsol"')


# --------------------------------------------------------------------------
# Lecture du zip
# --------------------------------------------------------------------------

def lire_zip(chemin_zip):
    fichiers = {}
    with zipfile.ZipFile(chemin_zip) as z:
        mauvais = z.testzip()
        if mauvais:
            abandonner(f'le zip est abîmé (entrée {mauvais}). Retéléchargez-le.')

        for info in z.infolist():
            if info.is_dir():
                continue
            nom = info.filename.replace('\\', '/')

            # Un zip ne doit jamais pouvoir écrire hors du projet.
            if nom.startswith('/') or '..' in Path(nom).parts:
                abandonner(f'chemin suspect dans le zip : {nom}')
            if not nom.startswith('src/'):
                abandonner(f'entrée inattendue dans le zip : {nom}')

            fichiers[nom] = z.read(info)

    if not fichiers:
        abandonner('le zip ne contient aucun fichier.')
    return fichiers


# --------------------------------------------------------------------------
# Annulation
# --------------------------------------------------------------------------

def annuler(projet, dossier):
    source = Path(dossier)
    if not source.is_absolute():
        source = projet / source
    if not source.is_dir():
        abandonner(f'sauvegarde introuvable : {source}')

    manifeste = source / 'MANIFESTE.txt'
    if not manifeste.is_file():
        abandonner(f'{source} ne ressemble pas à une sauvegarde du script '
                   '(MANIFESTE.txt absent).')

    dire(f'Restauration depuis {source}')
    dire()
    remis = supprimes = 0
    for ligne in manifeste.read_text(encoding='utf-8').splitlines():
        if not ligne.strip() or ligne.startswith('#'):
            continue
        etat, _, relatif = ligne.partition('\t')
        cible = projet / relatif

        if etat == 'REMPLACE':
            copie = source / relatif
            cible.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(copie, cible)
            dire(f'   rétabli   {relatif}')
            remis += 1
        elif etat == 'CREE':
            # Ce fichier n'existait pas avant : on le retire.
            if cible.is_file():
                cible.unlink()
                dire(f'   supprimé  {relatif}')
                supprimes += 1
            # …et le dossier avec, s'il n'avait été créé que pour lui.
            parent = cible.parent
            while parent != projet and parent.is_dir() and not any(parent.iterdir()):
                parent.rmdir()
                dire(f'   supprimé  {parent.relative_to(projet).as_posix()}/ (vide)')
                parent = parent.parent

    dire()
    dire(f'Terminé : {remis} fichier(s) rétabli(s), {supprimes} supprimé(s).')
    dire('Pensez à relancer une compilation pour vérifier.')


# --------------------------------------------------------------------------
# Programme principal
# --------------------------------------------------------------------------

def extraire_erreur(texte):
    """
    Astro affiche le message utile en tête et la pile d'appels ensuite.
    Prendre bêtement les dernières lignes ne montrerait que la pile, qui
    ne dit rien. On repart donc du premier marqueur d'erreur, et on coupe
    dès que commencent les « at ... » de la pile.
    """
    lignes = texte.splitlines()
    debut = next((i for i, l in enumerate(lignes)
                  if '[ERROR]' in l or 'error:' in l.lower()), None)
    if debut is None:
        return lignes[-20:] or ['(aucune sortie)']

    utiles = []
    for ligne in lignes[debut:debut + 30]:
        if ligne.strip().startswith('at ') and utiles:
            break
        utiles.append(ligne)
    return utiles


def main():
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument('--zip')
    ap.add_argument('--projet')
    ap.add_argument('--sans-build', action='store_true')
    ap.add_argument('--annuler')
    args = ap.parse_args()

    dire('=' * 68)
    dire('  Carnets sur sol — installation des modifications')
    dire('=' * 68)
    dire()

    projet = trouver_projet(args.projet)
    dire(f'Projet   : {projet}')

    if args.annuler:
        dire()
        annuler(projet, args.annuler)
        return

    chemin_zip = trouver_zip(args.zip)
    dire(f'Archive  : {chemin_zip}')
    dire()

    fichiers = lire_zip(chemin_zip)

    # --- constitution du plan -------------------------------------------
    a_remplacer, a_creer, identiques = [], [], []
    for relatif, contenu in sorted(fichiers.items()):
        cible = projet / relatif
        if not cible.exists():
            a_creer.append(relatif)
        elif hashlib.sha256(contenu).hexdigest() == somme(cible):
            identiques.append(relatif)
        else:
            a_remplacer.append(relatif)

    if not a_remplacer and not a_creer:
        dire('Tout est déjà à jour : aucun fichier à modifier.')
        return

    dire('CE QUI VA ÊTRE FAIT')
    dire('-' * 68)
    for r in a_creer:
        dire(f'   créé      {r}')
    for r in a_remplacer:
        dire(f'   remplacé  {r}   (l\'ancien est sauvegardé)')
    for r in identiques:
        dire(f'   inchangé  {r}')
    dire('-' * 68)
    dire()

    # --- état de git, à titre d'information ------------------------------
    if (projet / '.git').exists():
        try:
            sortie = subprocess.run(['git', 'status', '--porcelain'],
                                    cwd=projet, capture_output=True,
                                    text=True, timeout=30)
            if sortie.stdout.strip():
                dire('Note : votre dépôt git contient des modifications non '
                     'validées.')
                dire('       Ce n\'est pas bloquant (tout est sauvegardé de '
                     'toute façon),')
                dire('       mais un « git commit » avant serait plus propre.')
                dire()
        except Exception:
            pass

    reponse = input('Continuer ? (o/N) ').strip().lower()
    if reponse not in ('o', 'oui'):
        dire()
        dire('Annulé. Rien n\'a été modifié.')
        return

    # --- sauvegarde ------------------------------------------------------
    horodatage = datetime.now().strftime('%Y-%m-%d_%Hh%M')
    sauvegarde = projet / '.sauvegardes' / horodatage
    sauvegarde.mkdir(parents=True, exist_ok=True)

    lignes = ['# Généré par installer-modifs.py — ne pas modifier',
              f'# {datetime.now().strftime("%d/%m/%Y à %H:%M")}',
              f'# source : {chemin_zip}', '']

    for relatif in a_remplacer:
        copie = sauvegarde / relatif
        copie.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(projet / relatif, copie)
        lignes.append(f'REMPLACE\t{relatif}')
    for relatif in a_creer:
        lignes.append(f'CREE\t{relatif}')

    (sauvegarde / 'MANIFESTE.txt').write_text('\n'.join(lignes) + '\n',
                                              encoding='utf-8')
    dire()
    dire(f'Sauvegarde : {sauvegarde}')

    # --- écriture --------------------------------------------------------
    for relatif in a_remplacer + a_creer:
        cible = projet / relatif
        cible.parent.mkdir(parents=True, exist_ok=True)
        cible.write_bytes(fichiers[relatif])
    dire(f'Écrit      : {len(a_remplacer) + len(a_creer)} fichier(s)')

    # --- relecture : ce qui est sur le disque est-il bien ce qu'on voulait ?
    for relatif in a_remplacer + a_creer:
        if somme(projet / relatif) != hashlib.sha256(fichiers[relatif]).hexdigest():
            dire()
            dire(f'Copie incorrecte pour {relatif} — restauration.')
            annuler(projet, sauvegarde)
            sys.exit(1)

    if args.sans_build:
        dire()
        dire('Compilation non demandée (--sans-build).')
        dire('Vérifiez vous-même avec :  npx astro build')
        rappel(sauvegarde, projet)
        return

    # --- compilation d'essai ---------------------------------------------
    npx = shutil.which('npx')
    if not npx:
        dire()
        dire('npx introuvable : la compilation d\'essai est sautée.')
        dire('Lancez-la vous-même :  npx astro build')
        rappel(sauvegarde, projet)
        return

    dire()
    dire('Compilation d\'essai en cours (quelques minutes sur 3 300 notules)…')
    resultat = subprocess.run([npx, 'astro', 'build'], cwd=projet,
                              capture_output=True, text=True)

    if resultat.returncode != 0:
        dire()
        dire('LA COMPILATION A ÉCHOUÉ. Voici l\'erreur :')
        dire('-' * 68)
        for ligne in extraire_erreur(resultat.stdout + resultat.stderr):
            dire('   ' + ligne)
        dire('-' * 68)
        dire()
        dire('Restauration automatique de l\'état d\'origine.')
        dire()
        annuler(projet, sauvegarde)
        dire()
        dire('Votre site est intact. Envoyez-moi le message ci-dessus.')
        sys.exit(1)

    derniere = [l for l in resultat.stdout.splitlines() if 'page(s) built' in l]
    dire()
    dire('Compilation réussie.')
    if derniere:
        dire('   ' + derniere[-1].strip())

    rappel(sauvegarde, projet)


def rappel(sauvegarde, projet):
    relatif = sauvegarde.relative_to(projet)
    dire()
    dire('=' * 68)
    dire('Pour revenir en arrière :')
    dire(f'   python installer-modifs.py --annuler "{relatif}"')
    dire()
    dire('Pour publier, une fois le rendu vérifié :')
    dire('   git add -A && git commit -m "Césure, voisines, fil à 50, '
         'archives dépliées" && git push')
    dire('=' * 68)


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        dire()
        dire('Interrompu.')
        sys.exit(1)
