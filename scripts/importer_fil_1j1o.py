# -*- coding: utf-8 -*-
"""
Convertit le fil « Un jour, un opéra » (@carnetsol) en notules autonomes,
une par journée mentionnée, dans la catégorie « 1 jour 1 opéra ».

Source : https://threadreaderapp.com/thread/1641199519810584577.html

Chaque notule reçoit le même encart d'import automatique que les notules
récupérées après le crash de 2025 (classe CSS .recuperation, déjà stylée).

Usage :
    python scripts\\importer_fil_1j1o.py
    python scripts\\importer_fil_1j1o.py --ecrire
    python scripts\\importer_fil_1j1o.py --ecrire --distant     (pas de téléchargement)

Par défaut les images et vidéos sont RAPATRIÉES dans public/medias/1j1o/,
car les adresses pbs.twimg.com peuvent disparaître du jour au lendemain.
"""

import argparse
import json
import os
import re
import sys
import unicodedata
from datetime import datetime

# ---------------------------------------------------------------------------
# Réglages
# ---------------------------------------------------------------------------

CATEGORIE_NOM = "1 jour 1 opéra"
CATEGORIE_SLUG_DEFAUT = "1-jour-1-opera"

# Plage d'identifiants réservée : les notules Dotclear s'arrêtent vers 3460,
# aucun risque de collision avec un permalien existant.
POSTID_DEPART = 92001

AUTEUR = "DavidLeMarrec"
DOSSIER_MEDIAS = "public/medias/1j1o"
PREFIXE_MEDIAS = "/medias/1j1o"
PREFIXE_FICHIER = "import-1j1o"

SOURCE_FIL = "https://threadreaderapp.com/thread/1641199519810584577.html"

MARQUEUR = (
    '<p class="recuperation"><em>Récupéré automatiquement du fil Twitter '
    '« 1 jour, 1 opéra », le {date_lisible}. '
    '<a href="{source}" rel="noopener">Fil d\'origine</a>.</em></p>\n'
)

MARQUEUR_DATE_INCERTAINE = (
    '<p class="recuperation"><em>[date reconstituée : le fil indiquait '
    '« {tel_quel} », ce qui ne correspond ni au jour de la semaine annoncé '
    'ni à la chronologie des images ; à vérifier]</em></p>\n'
)

MARQUEUR_ENTETE_MANQUANT = (
    '<p class="recuperation"><em>[le tweet d\'ouverture de cette journée '
    'manque dans la capture Thread Reader ; date et lieu reconstitués '
    'd\'après les images et la suite du fil]</em></p>\n'
)

MOIS_FR = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet",
           "août", "septembre", "octobre", "novembre", "décembre"]


# ---------------------------------------------------------------------------
# Normalisation des faux styles Unicode
#
# Twitter n'a pas d'italique : on y trichait avec les blocs Mathematical
# Alphanumeric Symbols (𝐴𝑣𝑒𝑛𝑡𝑢𝑟𝑒𝑠, 𝐌𝐚𝐫𝐤) et les petites capitales (Kᴀʀᴏʟ).
# Sur un site web, ces caractères sont illisibles pour les lecteurs d'écran
# et introuvables par la recherche : on les ramène en texte + balise.
# ---------------------------------------------------------------------------

def _table(depart_maj, depart_min, chiffres=None):
    t = {}
    for i in range(26):
        t[chr(depart_maj + i)] = chr(ord("A") + i)
        t[chr(depart_min + i)] = chr(ord("a") + i)
    if chiffres:
        for i in range(10):
            t[chr(chiffres + i)] = chr(ord("0") + i)
    return t


ITALIQUE = {}
ITALIQUE.update(_table(0x1D434, 0x1D44E))            # mathematical italic
ITALIQUE.update(_table(0x1D608, 0x1D622))            # sans-serif italic
ITALIQUE["\U0001D455"] = "h"                          # trou du bloc italique

GRAS = {}
GRAS.update(_table(0x1D400, 0x1D41A, 0x1D7CE))       # mathematical bold
GRAS.update(_table(0x1D5D4, 0x1D5EE, 0x1D7EC))       # sans-serif bold

PETITES_CAPS = {
    "\u1D00": "a", "\u0299": "b", "\u1D04": "c", "\u1D05": "d", "\u1D07": "e",
    "\uA730": "f", "\u0262": "g", "\u029C": "h", "\u026A": "i", "\u1D0A": "j",
    "\u1D0B": "k", "\u029F": "l", "\u1D0D": "m", "\u0274": "n", "\u1D0F": "o",
    "\u1D18": "p", "\u0280": "r", "\uA731": "s", "\u1D1B": "t", "\u1D1C": "u",
    "\u1D20": "v", "\u1D21": "w", "\u028F": "y", "\u1D22": "z",
}


def _convertir_runs(texte, table, balise):
    """Remplace les suites de caractères stylisés par du texte balisé."""
    sortie = []
    tampon = []

    def vider():
        if tampon:
            sortie.append("<%s>%s</%s>" % (balise, "".join(tampon), balise))
            tampon.clear()

    for ch in texte:
        if ch in table:
            tampon.append(table[ch])
        elif tampon and ch in " '’-.":
            # on reste dans le run : « 𝐌𝐚𝐫𝐤 𝐌𝐢𝐧𝐤𝐨𝐯 » est un seul nom
            tampon.append(ch)
        else:
            vider()
            sortie.append(ch)
    vider()
    resultat = "".join(sortie)
    # un run peut avoir avalé une espace finale : on la ressort de la balise
    resultat = re.sub(r"(\s+)</%s>" % balise, r"</%s>\1" % balise, resultat)
    return resultat


def normaliser_styles(texte):
    texte = _convertir_runs(texte, GRAS, "strong")
    texte = _convertir_runs(texte, ITALIQUE, "em")
    texte = _convertir_runs(texte, PETITES_CAPS, "span")
    # les petites capitales redeviennent des majuscules simples
    texte = re.sub(r"<span>([^<]*)</span>",
                   lambda m: m.group(1).upper(), texte)
    return texte


def echapper(texte):
    return (texte.replace("&", "&amp;")
                 .replace("<", "&lt;")
                 .replace(">", "&gt;"))


def enrichir(texte):
    """Échappe le HTML, puis restitue italiques, liens et mentions."""
    texte = echapper(texte)
    texte = normaliser_styles(texte)
    # **nom** = gras ; *titre* et /titre/ = italique (conventions du fil)
    texte = re.sub(r"\*\*([^*\n]+)\*\*", r"<strong>\1</strong>", texte)
    texte = re.sub(r"\*([^*\n]+)\*", r"<em>\1</em>", texte)
    texte = re.sub(r"(?<![\w:/])/([^/\n]{2,60})/(?![\w])", r"<em>\1</em>", texte)
    # adresses nues
    texte = re.sub(r"(?<!\")(https?://[^\s<]+)",
                   r'<a href="\1" rel="noopener">\1</a>', texte)
    # mentions @ vers X
    texte = re.sub(r"(?<![\w@/])@(\w{2,15})\b",
                   r'<a href="https://x.com/\1" rel="noopener nofollow">@\1</a>',
                   texte)
    # mots-dièse
    texte = re.sub(r"(?<![\w#])#(\w{2,40})\b", r"<span class=\"motdiese\">#\1</span>",
                   texte)
    return texte


def slugifier(valeur):
    """Slug façon Dotclear, sans caractère interdit sous Windows."""
    valeur = unicodedata.normalize("NFD", valeur)
    valeur = "".join(c for c in valeur if unicodedata.category(c) != "Mn")
    valeur = valeur.lower()
    valeur = re.sub(r"[^a-z0-9]+", "-", valeur)
    valeur = re.sub(r"-{2,}", "-", valeur).strip("-")
    return valeur or "notule"


def texte_seul(html):
    html = re.sub(r"<[^>]+>", " ", html)
    html = (html.replace("&amp;", "&").replace("&lt;", "<")
                .replace("&gt;", ">").replace("&nbsp;", " "))
    return re.sub(r"\s+", " ", html).strip()


def date_lisible(d):
    return "%d %s %d" % (d.day, MOIS_FR[d.month - 1], d.year)


# ---------------------------------------------------------------------------
# Le fil, découpé par journée
#
# Chaque bloc = un tweet : son texte, ses images, ses vidéos, ses vidéos
# YouTube. L'ordre est celui du fil.
# ---------------------------------------------------------------------------

def i(nom):
    return "https://pbs.twimg.com/media/" + nom


def v(nom):
    return "https://video.twimg.com/tweet_video/" + nom


JOURNEES = [
    {
        "date": "2020-01-15",
        "lieu": "Kaunas",
        "oeuvre": "Mr X.",
        "compositeur": "Kálmán",
        "blocs": [
            {"t": "Un jour, un opéra.\n\n🔵 Aujourd'hui, 15 janvier, à Kaunas, "
                  "au centre de la Lithuanie, on donne *Mr X.*, adaptation "
                  "(en lithuanien ?) de *Die Zirkusprinzessin* de Kálmán, une "
                  "pièce légère d'un compositeur dans le top 10 des plus joués "
                  "au monde.",
             "img": [i("EOVFpU3W4AI2eUf.jpg"), i("EOVFp4AXUAUcZSR.jpg"),
                     i("EOVFqP9X4AM1DqB.jpg")]},
        ],
    },
    {
        "date": "2021-06-07",
        "entete_manquant": True,
        "lieu": "Tel-Aviv",
        "oeuvre": "l'Opéra d'Israël",
        "compositeur": "David Sebba",
        "titre_force": "07/06/21 : Sebba (à Tel-Aviv)",
        "blocs": [
            {"t": "La première œuvre programmée fut La Traviata : la compagnie "
                  "se produisait alors dans les cinémas, et privilégia longtemps "
                  "le répertoire italien.\n\n(Avec de très belles affiches de "
                  "vedettes du Met et d'Europe, dès les années 70-80.)",
             "img": [i("E3VqyNEWQAE7guM.jpg")]},
            {"t": "Le premier opéra en hébreu, *Dan the guard* (Dan la sentinelle "
                  "/ le pionnier ?) de Marc LAVRY, date de 1942 et se tient dans "
                  "un kibboutz (d'avant l'indépendance, donc).",
             "img": [i("E3VrinIWQAE6f-l.jpg")]},
            {"t": "Le bâtiment actuel, dans le Centre des Arts Vivants de "
                  "Tel-Aviv, à la new-yorkaise, ouvre en 1994.",
             "img": [i("E3VtXgPWQAUQ5z8.jpg")]},
            {"t": "La musique de David SEBBA joue de codes connus : le ton "
                  "général est plutôt celui de la musique légère viennoise ou "
                  "des pièces les moins solennelles de Verdi (coucou le "
                  "triangle !)."},
        ],
    },
    {
        "date": "2021-06-08",
        "lieu": "Astana",
        "oeuvre": "Birzhan – Sara",
        "compositeur": "Mukan Tulebayev",
        "blocs": [
            {"t": "🔵 Ce 8 juin,\n\nà l'Opéra d'Astana (ville de Nour-Soultan "
                  "depuis 2019 en l'honneur du tyranneau local),\n\non donne "
                  "*Birzhan – Sara* de Mukan TULEBAYEV, un des grands standards "
                  "de l'opéra kazakh et de l'art national.",
             "img": [i("E3XQ1onX0AczIig.jpg")]},
            {"t": "La maison se glorifie de montrer « dès la première scène » "
                  "des artisans traditionnels, « des marchands âpres, des "
                  "funambules adroits et des chasseurs à l'aigle montés à "
                  "cheval », magnifiés par la 3D, les costumes éclatants, les "
                  "installations vidéo !\n\n(Pas très eurotrash donc.)",
             "img": [i("E3XRu0gXMAgmQmc.jpg")]},
            {"t": "Le livret raconte la séparation par un rapt de deux aqyns "
                  "(chanteurs) qui mène leur aytysh (sorte de concert-compétition "
                  "dans le style récitatif, alla Tannhäuser) : Sara doit être "
                  "mariée de force, & lors de sa fuite, elle est poignardée – "
                  "ou son amant Birzhan, plusieurs versions.",
             "img": [i("E3X58OJWEAEaFyH.jpg")]},
            {"t": "La construction de l'opéra (sur des plans inspirés, dit-on, "
                  "par le tyranneau Nazarbaïev) s'étend de 2010 à 2013.\n\n"
                  "Quoique le plus vaste théâtre d'Asie centrale (assure-t-il), "
                  "l'orchestre & la troupe sont formés de jeunes musiciens : je "
                  "ne trouve pas trace d'une troupe antérieure ?",
             "img": [i("E3X9W0wXoAQlSFc.jpg")]},
            {"t": "Quant à la musique ? Très belle, très simple, elle évoque "
                  "essentiellement l'opéra russe du XIXe siècle (et même les "
                  "chants orthodoxes), avec des séquences instrumentales "
                  "simplifiées et assez joyeuses.",
             "yt": ["_pXm4OiIupc"]},
        ],
    },
    {
        "date": "2021-06-09",
        "lieu": "Olomouc",
        "oeuvre": "Na tý louce zelený",
        "compositeur": "Jára Beneš",
        "blocs": [
            {"t": "🔵 Ce 9 juin,\n\nau Théâtre Morave d'Olomouc (au Nord-Est de "
                  "la République Tchèque, entre Brno et Ostrava),\n\non donne "
                  "*Na tý louce zelený* (Sur le pré vert) de Jára Beneš, un des "
                  "grands standards de l'opérette tchèque.",
             "img": [i("E3a4ikhXwAIA1Mm.jpg")]},
            {"t": "Créée en tchèque en 1935 à Nusle, puis en allemand en 1936 à "
                  "la Volksoper de Vienne, elle met en scène un propriétaire "
                  "terrien qui a transmis son bien à sa fille aux idées "
                  "réformatrices – les personnages principaux sont ainsi un "
                  "ingénieur forestier et un professeur d'agriculture !",
             "img": [i("E3c3Qe3XEAMy1pe.jpg")]},
            {"t": "Au XVIIIe siècle et à son plus fort dans les années 1840, la "
                  "spécialité locale était les hanácké opery – les opéras Haná, "
                  "opéras à sujet folklorique dans un dialecte spécifique, tout "
                  "un genre (à rapprocher de l'opéra comique et du singspiel ?) "
                  "qui était à son faîte lors…",
             "img": [i("E3dJtQsXEAYus20.jpg")]},
            {"t": "… lors de l'édification du théâtre actuel (1828-1830), en "
                  "plein tissu urbain préexistant.",
             "img": [i("E3dJ5clX0AI_pHc.jpg")]},
            {"t": "En tant que telle, la troupe actuelle, l'une des 4 grandes "
                  "maisons de Moravie (avec Brno, Ostrava et Opava) est fondée "
                  "en 1920, soit pour cette fois bien plus tard que le théâtre "
                  "lui-même, étrangement.\n\n(Je n'ai pas encore trouvé "
                  "d'explications.)",
             "img": [i("E3dK-N9XEAcAqZZ.jpg")]},
        ],
    },
    {
        "date": "2021-06-10",
        "lieu": "Almaty",
        "oeuvre": "Kyz Zhibek",
        "compositeur": "Yevgeny Brusilovsky",
        "blocs": [
            {"t": "🔵 Ce 10 juin,\n\nà l'Opéra d'Abay (sis à Almaty, au Sud-Est "
                  "du Kazakhstan, à la frontière avec le Kirghizistan),\n\non "
                  "donne *Kyz Zhibek* (Қыз Жібек), de Yevgeny BRUSILOVSKY,\n\n"
                  "considéré comme le premier opéra kazakh (1934) et créé dans "
                  "cette même maison l'année de son édification.",
             "img": [i("E3f9jLvWUAQrfOo.jpg")]},
            {"t": "Le sujet est tiré d'un poème folklorique du XVIe siècle, sur "
                  "l'histoire d'un Roméo & Juliette local.\n\nLes familles autour "
                  "de (la belle) Zhibek et (du valeureux guerrier) Tolegen sont "
                  "opposées, et ce dernier est traîtreusement assassiné par "
                  "Bekejan, un rival.",
             "img": [i("E3gCsChXMAE8h-q.jpg")]},
            {"t": "Après quoi Zhibek, en héroïne bien élevée, se tue.",
             "img": [i("E3iKdpMXwAYWLQ9.jpg")]},
            {"t": "Le théâtre tire son nom du compositeur, poète, philosophe et "
                  "théologien (islamique) kazakh Abai Qunanbaiuly (1845-1906), "
                  "et non de la ville d'Almaty.",
             "img": [i("E3iLIvMWQAA8NZt.jpg"), i("E3iLI3XXEAEJ_ox.jpg"),
                     i("E3iLJTUXwAkYOiI.jpg")]},
            {"t": "Bâti de 1934 à 1941, ceinturé de verdure et quasiment au pied "
                  "des montagnes, l'Opéra d'Almaty est marqué, me semble-t-il, "
                  "par une forte influence persane !",
             "img": [i("E3lGAElWEAAM5F4.jpg"), i("E3lGAMcWUAMh3VP.jpg"),
                     i("E3lGAlzXoAIbjdq.jpg")]},
            {"t": "Quant à la musique de Brusilovsky, elle emprunte avec beaucoup "
                  "de vivacité, trouvé-je, au folklore et à une tradition "
                  "d'orchestration ballettistique de qualité.\n\n(Car, oui, on y "
                  "trouve de belles pièces de ballet.)",
             "yt": ["saLRdMSQTlo"]},
            {"t": "Il n'existe, si j'ai compris les lectures, qu'une toute petite "
                  "portion (une dizaine) d'opéras en kazakh – il faut dire qu'il "
                  "y a peu de maisons d'Opéra dans le pays, que le genre y est "
                  "récent et le répertoire joué largement du patrimoine italien "
                  "et russe.",
             "img": [i("E3lHi4sWUAI4_Eh.jpg"), i("E3lHjSTWEAA6uAJ.jpg"),
                     i("E3lHjnGWYAYb-lR.jpg")]},
            {"t": "Et le lendemain…\n\n#AlerteGlottophilie",
             "img": [i("E3lIeaZXwAAb5mM.jpg")]},
            {"t": "Ce même jour, à Minsk (Bélarus) on joue la Fiancée du Tsar – "
                  "quelle jolie allégorie que ce criminel qui s'éprend de ce "
                  "petit bout de chou et le 'protège' façon pizzo), et à Lviv",
             "img": [i("E3lKupsX0AALPKY.jpg")]},
            {"t": "et à Lviv (tout à l'Ouest de l'Ukraine) on joue Turandot – "
                  "histoire d'une princesse-impératrice sanguinaire et archaïque "
                  "qui opprime et détruit ceux qui l'aiment.\n\nAucun message "
                  "politique là non plus, évidemment.",
             "img": [i("E3lK8AzXwAUrFGI.jpg")]},
        ],
    },
    {
        "date": "2022-01-03",
        "lieu": "Perm",
        "oeuvre": "Adventures in the Land of Opera",
        "compositeur": "Mark Minkov",
        "blocs": [
            {"t": "🔵 Ce lundi 3 janvier 2022, à Perm,\n\non joue "
                  "*Adventures in the Land of Opera* (1974) de "
                  "**Mark Minkov**,\n"
                  "dans sa version révisée de 2000.\n\nUn ouvrage conçu pour "
                  "initier le jeune public, beaucoup de créations de ce type en "
                  "Russie.",
             "img": [i("FIKJIRTXEAEEG85.jpg")]},
            {"t": "La princesse Slezabeta est inconsolable, le Diamant Bleu a été "
                  "dérobé dans le palais du Roi II et de la reine Zevunya XIII.\n\n"
                  "Le Détective se met en action, accompagné des clowns Triste et "
                  "Joyeux qui font chanter le public.\n\n(Ce n'est pas fini.)",
             "img": [i("FIKKyecXIAAk-_7.jpg")]},
            {"t": "Interviennent aussi les instruments de l'orchestre, comme des "
                  "personnages, pour les rendre familiers au jeune public (à "
                  "partir de 4 ans).\n\nLe tout culminant dans la Danse des Petits "
                  "Cygnes réalisée par des pingouins savants.",
             "img": [i("FIKLRDzX0AEOcdE.jpg")]},
            {"t": "Je ne connais de Minkov que de la chanson symphonique : ce doit "
                  "être très accessible."},
            {"t": "L'étrange Currentzis en est le directeur musical, et la troupe "
                  "a (brièvement) été fusionnée avec son ensemble MusicAeterna.",
             "img": [i("FIKPou5WUAE_qfe.jpg"), i("FIKPo2iXEAAFxR2.jpg"),
                     i("FIKPo98WYAEfBIe.jpg"), i("FIKPpF4WYAEMscI.jpg")]},
        ],
    },
    {
        "date": "2022-01-04",
        "date_douteuse": "mardi 4 février 2022",
        "lieu": "Umeå",
        "oeuvre": "Kejsarens nya kläder",
        "compositeur": "Miloš Vacek",
        "blocs": [
            {"t": "🔵 Ce mardi 4 février 2022,\n\nau Norrlandsopera (Umeå),\n\non "
                  "donne *Kejsarens nya kläder* (« Les Habits neufs de l'Empereur »)"
                  "\nde **Miloš Vacek**,\n\n"
                  "adaptation en suédois de cette production allemande pour la "
                  "jeunesse d'après Andersen – un pot-pourri.",
             "img": [i("FIPc0zeWYAAqNnS.jpg")]},
            {"t": "Je n'ai pas pu accéder à la musique, mais d'après le programme "
                  "de l'Opéra d'Umeå, il s'agit d'un mélange de musique "
                  "traditionnelle tchèque, de cabaret allemand, de Puccini, de "
                  "Weill.\n\nEt comme tout le monde connaît l'histoire, je n'ai "
                  "plus qu'à vous parler du lieu :",
             "img": [i("FIPd3URXwAAGaxT.jpg")]},
            {"t": "J'avais écrit ceci :\n\n« Ainsi que vous l'a peut-être suggéré "
                  "le plafond (ainsi que l'élégant extérieur 🧐 ), il s'agit "
                  "*réellement* d'une "
                  "caserne de pompiers (de 1937, architectes Wejke & Ödeen), "
                  "retravaillée par Olle Qvarnström pour l'inauguration de "
                  "1984. »\n\nMAIS",
             "img": [i("FIPfLOiWQAEpsCs.jpg")]},
            {"t": "… en relisant mes sources, je vois que la salle actuelle date "
                  "de 2002 (la gaffe 😅 ), sauf qu'elle est située dans "
                  "l'ancienne Maison d'Opéra.\n\nJe ne sais donc plus trop ce que "
                  "je vois. (Quoi qu'il en soit, ça ressemble à un hangar à "
                  "pimpon.)",
             "img": [i("FIPgCd-WUAAc_vF.jpg")]},
            {"t": "La compagnie existe depuis 1974, fondée par Arnold Östman "
                  "(connu pour ses très bons enregistrements de Mozart avec "
                  "l'orchestre sur crincrins de Drottningholm), comme toujours "
                  "issue de l'installation d'une troupe préexistante.",
             "img": [i("FIPhZx0X0AEcPE_.jpg")]},
            {"t": "Depuis, Norrlandsoperan a établi son propre orchestre, "
                  "successivement dirigé depuis 1995 par rien de moins que Roy "
                  "Goodman, Kristjan Järvi ou Rumon Gamba !\n\n(Navré, ce n'est "
                  "pas aussi croustillant que les opéras rasés d'Europe centrale.)",
             "img": [i("FIPiq4iX0AI6OOL.jpg")]},
        ],
    },
    {
        "date": "2022-01-07",
        "date_douteuse": "vendredi 7 février 2022",
        "lieu": "Osnabrück",
        "oeuvre": "Fremde Erde",
        "compositeur": "Karol Rathaus",
        "blocs": [
            {"t": "🔵 Ce vendredi 7 février 2022,\n\nà Osnabrück (en Basse-Saxe, "
                  "au Nord-Est de Münster),\n\nça ne va pas beaucoup rigoler : on "
                  "donne *Fremde Erde* (« Terre étrangère ») de KAROL RATHAUS,"
                  "\n\nopéra sur la "
                  "migration ouvrière aux USA et la misère en Europe.",
             "img": [i("FIe5BTuWYAM5W7Z.jpg")]},
            {"t": "¶ Rathaus, né en 1895 en Galicie, juif, étudie auprès de "
                  "Schreker et rencontre un réel succès public. Dans les années "
                  "1920, il est professeur de composition et de théorie musicale "
                  "à Berlin.\n\nPuis devant la montée du nazisme, il vit la vie "
                  "des exilés, à Paris, Londres, New York."},
            {"t": "Sa carrière se finit comme professeur de composition dans la "
                  "nouvelle université du Queens.\n\nMais cet opéra date de 1930, "
                  "avant sa propre vie d'exil !"},
            {"t": "¶ L'intrigue est assez terrible : des paysans lituaniens sont "
                  "sur un paquebot. L'héritière d'une mine de salpêtre le repère "
                  "pour sa force (#TragédieFlorentine) et le séduit à force "
                  "d'argent et de caresses, si bien qu'il abandonne sa fiancée "
                  "pour partir comme mineur.",
             "vid": [v("FIhUbbpXoAYlg5W.mp4")]},
            {"t": "Évidemment, la réalité se révèle terrible, et l'argent "
                  "faramineux qu'elle a promis à Semjin au bout d'une année se "
                  "révèle un leurre, dans la mesure où personne ne survit plus de "
                  "quelques mois.\n\nRévolté, il fait venir par ruse l'héritière "
                  "un jour d'enterrement :",
             "vid": [v("FIhVN5zXsAQlyL1.mp4")]},
            {"t": "furieuse, elle l'humilie et paie les ouvriers pour l'exécuter. "
                  "La sentence n'est suspendue que lorsque, moribond, elle le "
                  "chasse !\n\nMéditant le suicide dans le port de New York, il "
                  "trouve sa fiancée Anschutka mourante, ayant pris la fièvre et "
                  "trop pauvre pour payer",
             "vid": [v("FIhWXo_WUAA8Np3.mp4")]},
            {"t": "un médecin ou un billet retour.\n\nElle meurt dans ses bras, et "
                  "Semjin part en quête d'un travail qui le fasse mourir pour de "
                  "bon.",
             "vid": [v("FIhW1IzXEAMSHvU.mp4")]},
            {"t": "¶ Bien que Rathaus ait intégré le dodécaphonisme et le jazz "
                  "dans ses œuvres, j'entends plutôt ici les grands unissons "
                  "menaçants qui émaillent les thèmes de ses symphonies.\n"
                  "Les lignes vocales ne sont pas forcément élégantes, mais "
                  "parviennent à participer de l'intensité dramatique.",
             "vid": [v("FIiQY7EWUAIhnrO.mp4")]},
            {"t": "¶ Le théâtre actuel Jugendstil, de 1909, n'est évidemment pas "
                  "le début du théâtre musical à Osnabrück, présent dès 1771 à la "
                  "Cour locale, puis étendu à deux maisons anciennement "
                  "aristocratiques (où officia notamment Lortzing !) à partir de "
                  "1780, ouvert à la ville.",
             "img": [i("FInFMGWXsAM-tpF.jpg")]},
        ],
    },
    {
        "date": "2022-01-10",
        "date_douteuse": "lundi 7 janvier 2022",
        "lieu": "Vienne",
        "oeuvre": "Thérèse Raquin",
        "compositeur": "Tobias Picker",
        "blocs": [
            {"t": "🔵 Ce lundi 7 janvier 2022,\n\nau Theater an der Wien,\n\non "
                  "donne *Thérèse Raquin* (2000),\n\ntroisième "
                  "opéra de TOBIAS PICKER (son septième est programmé "
                  "pour 2023),\n\nd'après le roman de Zola.",
             "img": [i("FIuQMnTWUAAOCG7.jpg")]},
            {"t": "¶ La musique de Picker, plutôt tonale et pourvue de cordes très "
                  "lyriques postpucciniennes, nous apparaît, mélomanes européens, "
                  "très américaine ; mais à l'échelle de ce qui se joue à l'Opéra, "
                  "c'est en réalité une musique assez audacieuse,",
             "yt": ["ri42c_1nxKs"]},
            {"t": "dont l'harmonie a senti passer Berg (légèrement) et "
                  "Chostakovitch – via, bien sûr, des prédécesseurs américains "
                  "(on est nettement au-delà des symphonies de Bernstein !).\n\n"
                  "L'usage des percussions dramatiques, aussi.\n\n(Vidéo de la "
                  "création.)"},
            {"t": "¶ L'histoire de Th. Raquin est assez connue et/ou documentée "
                  "pour ne pas être racontée, mais le librettiste tire un bon "
                  "parti des scènes d'assassinat – avec des modifications de "
                  "déroulé par rapport à la source."},
            {"t": "¶ Le Theater an der Wien est aujourd'hui le théâtre ambitieux "
                  "de Vienne – un peu comme l'Opéra-Comique à Paris : du baroque, "
                  "des œuvres moins courues (mais parfois à grand effectif !).\n\n"
                  "C'est un peu là que se passe l'action, à côté des reprises du "
                  "Rosenkavalier de Schenck…",
             "img": [i("FIwPHEjWQAEmdYz.jpg")]},
            {"t": "Il tire son nom de la rivière homonyme, aujourd'hui couverte "
                  "par le théâtre et les bâtiments alentours.\n\nLe projet est dû "
                  "à Schikaneder, le librettiste et commanditaire de la Flûte "
                  "enchantée, et aboutit en 1801."},
            {"t": "Parmi les œuvres créées là, beaucoup Beethoven (s2, s3, s5, s6, "
                  "Fidelio…), Rosamunde de Schubert, Die Fledermaus de J. Strauß "
                  "II, Die lustige Witwe de Lehár !\n\nLes Talens Lyriques y sont "
                  "souvent (Salieri…), on y a aussi donné Dalibor de Smetana, et "
                  "autres œuvres inhabituelles."},
        ],
    },
    {
        "date": "2023-03-29",
        "lieu": "Tallinn",
        "oeuvre": "Buratino",
        "compositeur": "Olav Ehala",
        "blocs": [
            {"t": "🔵 Ce 29 mars 2023,\n\non donne, au Rahvusooper Estonia (Opéra "
                  "National d'Estonie),\n\nBuratino d'Olav EHALA, compositeur "
                  "estonien (né en 1950), une comédie musicale d'après Collodi et "
                  "Tolstoï. En estonien évidemment.",
             "img": [i("Fsayr8XWIAEKy6q.jpg")]},
            {"t": "Le livret s'inspire de La Clef d'or, le pastiche de Pinocchio "
                  "que Tolstoï a prétendu recréer d'après ses souvenirs d'enfance "
                  "(ce qui est faux, il l'a manifestement lu à l'âge adulte et "
                  "voulu créer sa propre version).\n\nLe librettiste, Andres "
                  "Dvinjaninov, l'a mêlé au conte italien.",
             "img": [i("FsaznkZWcAMzu8b.png")]},
            {"t": "Chanteurs amplifiés, musique simple et directe de comédie "
                  "musicale, mais avec çà et là quelques effets orchestraux plus "
                  "audacieux. Je trouve ça très bien écrit. (Et avec la saveur de "
                  "la langue locale, cousine du finnois, un petit bonbon… !)",
             "yt": ["W_JK2UZFcrc"]},
            {"t": "L'histoire de l'opéra en Estonie est assez récente : ce n'est "
                  "qu'en 1870 qu'on trouve une première société musicale de "
                  "théâtre lyrique, « Estonia ».\n\nSans doute du fait, comme pour "
                  "l'Ukraine, du poids des tutelles politiques environnantes.\n\n"
                  "Le théâtre, lui, date de 1913.",
             "img": [i("Fsa0buWXgAclaxn.jpg")]},
            {"t": "Les dates m'amusent.\n\n1907 – première opérette Mam'zelle "
                  "Nitouche d'Hervé\n1908 – premier opéra, Das Nachtlager in "
                  "Granada (Kreutzer)\n1911 – première opérette estonienne (La "
                  "Nuit de la Saint-Jean de Wirkhaus)"},
            {"t": "1922 – premier ballet représenté, Coppélia de Delibes\n1928 – "
                  "premier opéra écrit en langue estonienne (Les Vikings estoniens "
                  "d'Evald Aav)\n1944 – premier ballet estonien, Kratt "
                  "(évidemment sur une musique de Tubin)\n\n(Il y a d'autres "
                  "maisons slaves où le ballet arrive très tôt.)"},
            {"t": "Je suis frappé aussi par l'absence d'ostentation et la petite "
                  "jauge (il y a moins de places qu'au Marigny !).\n\nIl faut dire "
                  "que c'est un pays d'un million d'habitants, et une ville de "
                  "400.000 ! Les proportions ne sont pas les mêmes.",
             "img": [i("Fsa2DdbXoAQ70w9.png")]},
            {"t": "(Au demeurant, des villes russes de plus de deux millions "
                  "d'habitants ont parfois des théâtres de taille assez contenue.)"},
        ],
    },
    {
        "date": "2023-03-30",
        "lieu": "Cottbus",
        "oeuvre": "Alzheim",
        "compositeur": "Xavier Dayer",
        "blocs": [
            {"t": "🔵 Ce 30 mars 2023,\n\nau Staatstheater de Cottbus (le seul "
                  "théâtre d'État du Brandebourg, dans cette ville de 100.000 "
                  "habitants),\n\non donne /Alzheim/ du compositeur genevois "
                  "Xavier DAYER, un opéra d'une heure autour de la fameuse "
                  "maladie neurodégénérative.",
             "img": [i("FsctGWbWwAE2SUr.jpg")]},
            {"t": "Musique accessible (atonalité avec des pôles d'appui et des "
                  "progressions assez intuitives) ; le projet de Dayer était de "
                  "travailler sur l'intervalle qui sépare la tragédie des proches "
                  "de l'isolement irrémédiable du malade.",
             "yt": ["8GDLnEJSPH4"]},
            {"t": "Pour ce faire, il utilise symboliquement les opposés en "
                  "hauteur, aigu et grave (son « Urklang »), mais aussi des débits "
                  "trop lents ou trop rapides, des silences soudains,",
             "img": [i("FscvMVdWAAESG7z.jpg")]},
            {"t": "mais aussi l'écho d'une chanson du XIXe siècle (avec un "
                  "intervalle de sixte caractéristique) chantée par l'aide-"
                  "soignante et reprise comme motif récurrent…\n\nUn beau sujet "
                  "pour de l'opéra d'aujourd'hui !",
             "img": [i("FsdUZqEWYAAR53Q.jpg")]},
            {"t": "Les chiffres du Théâtre d'État de Cottbus me fascinent : seul à "
                  "porter ce titre dans le Brandebourg (depuis 1992), il rayonne."
                  "\n\n130.000 spectateurs annuels pour… 100.000 habitants !\n\n"
                  "Je pensais qu'on ne voyait ce genre de ratio que dans les "
                  "capitales touristiques !",
             "img": [i("FsdaFA7X0AEhXlW.jpg")]},
            {"t": "Vous pouvez constater vous-même la petite jauge. Le bâtiment "
                  "est dû à Sehring, l'architecte du Theater des Westens à Berlin, "
                  "suite à un concours et une commande financés grâce aux revenus "
                  "de l'industrie textile de la ville.\n\nInauguration en 1908 "
                  "avec une pièce de Lessing.",
             "img": [i("Fsdbi30XgAA_c3N.png")]},
            {"t": "Une partie des représentations ont lieu sur la 'scène de "
                  "chambre' (#3), dans un style un peu moins Art Nouveau / "
                  "Sécession que le bâtiment principal.",
             "img": [i("Fsdbr4CWAAMiokP.jpg"), i("Fsdb2WwWIAE49CL.jpg"),
                     i("Fsdb5fIXsAE8U9m.jpg")]},
            {"t": "Mais bon, c'est l'Allemagne. Quand on voit que Duisbourg (plus "
                  "petit que Massy) a un orchestre sensiblement du niveau des "
                  "meilleures phalanges parisiennes, on mesure l'autre monde dans "
                  "lequel on met les pieds !"},
        ],
    },
    {
        "date": "2023-04-01",
        "lieu": "Tacoma",
        "oeuvre": "The Tacoma Method",
        "compositeur": "Gregory Youtz",
        "blocs": [
            {"t": "🔵 Ce 1er avril 2023,\n\nau Rialto Theater de Tacoma (en "
                  "périphérie Sud de Seattle),\n\non joue un nouvel opéra de "
                  "Gregory YOUTZ à sujet historique et local, /The Tacoma Method/.",
             "img": [i("FspYlhYWwAMPtZv.jpg")]},
            {"t": "L'expression 'Tacoma Method' est historique, empruntée à "
                  "l'éloge d'un journaliste de la fin du XIXe siècle à propos de "
                  "l'expulsion de la communauté chinoise de Tacoma le 3 novembre "
                  "1885 : c'était la bonne façon, méthodique et définitive, de se "
                  "débarrasser des communautés chinoises.",
             "img": [i("FsslB0DWcAAnZeG.jpg")]},
            {"t": "Dès 1882, le Chinese Exclusion Act avait rendu l'immigration "
                  "chinoise illégale aux USA.\n\nSous l'impulsion du maire, le "
                  "raid est préparé : les portes et fenêtres sont brisées, les "
                  "résidents conduits de force à la gare pour acheter un billet, "
                  "ou forcés de parcourir à pied",
             "img": [i("Fss_aZGX0AE-24K.jpg")]},
            {"t": "les 140 miles jusqu'à Portland.\n\nIl y eut un procès de 27 "
                  "personnes (sur plusieurs centaines), mais aucun ne fut condamné "
                  "pour des crimes.\n\nS'ensuivit un débat, mais aussi, pour "
                  "partie, une célébration de cette action dans tout le pays.",
             "yt": ["4mkXzZRXpfg"]},
            {"t": "¶ Musicalement, du contemporain un peu triste (pas du tout de "
                  "l'avant-garde, mais peu de mélodies plaisantes), mais qui tisse "
                  "astucieusement des liens avec l'opéra traditionnel chinois, "
                  "j'ai l'impression – j'y entends les percussions répétées de "
                  "l'opéra du Sichuan, ou",
             "img": [i("FstclRMWAAAPkK6.jpg")]},
            {"t": "des doublures de synthétiseur qui sonnent comme des doublures "
                  "de cordes frottées caractéristiques du kunqu.\n\nEn tout cas "
                  "une belle initiative pour mettre en valeur la mémoire locale.",
             "img": [i("Fstdm7VX0AQMS25.jpg")]},
            {"t": "¶ Pour cette production, le lieu choisi est un ancien cinéma."
                  "\n\nBien qu'il soit la seconde plus grande compagnie du Nord de "
                  "la côte Pacifique, Tacoma Opera n'a été fondé qu'en 1968 ; "
                  "faillite à la fin des années 1970.",
             "img": [i("FsteboXWIAEwHAM.jpg")]},
            {"t": "En 1981, le chargé des relations avec le public de l'Opéra de "
                  "Seattle (même agglomération urbaine) fait revivre la compagnie "
                  "en mobilisant la Pacific Lutheran University, et la maison vit "
                  "depuis."},
        ],
    },
    {
        "date": "2023-04-18",
        "lieu": "Chicago",
        "oeuvre": "Champion",
        "compositeur": "Terence Blanchard",
        "blocs": [
            {"t": "🔵 Ce 18 avril 2023,\n\nle Lyric Opera of Chicago\n\ndonne "
                  "/Champion/, reprise d'un « opera in jazz » créé en 2013 autour "
                  "du destin d'un boxeur vedette des mi-moyens,\n\ndu trompettiste "
                  "de jazz et compositeur de musique de film Terence Blanchard,\n\n"
                  "sur un livret de Michael Cristofer.",
             "img": [i("Ft-epmOXsAM0rd7.jpg")]},
            {"t": "Tout est centré autour de la vie d'Emile Griffith (boxeur "
                  "réel), très marqué par la mort de son adversaire sous ses "
                  "coups, et cherchant sa place en tant que bisexuel dans un monde "
                  "aux représentations très virilisantes.",
             "img": [i("Ft-f8jTXsAAy3fc.jpg")]},
            {"t": "L'opéra a connu un certain succès (créé à St. Louis, repris au "
                  "Met de New York…), et sa musique se fonde sur l'ajout d'un trio "
                  "de jazz et d'un chœur de gospel à l'orchestre traditionnel de "
                  "l'opéra… Style transversal (je n'ai pas pu l'écouter).",
             "yt": ["0WTRzqCxSx0?start=120"]},
            {"t": "Le premier opéra joué à Chicago fut La Sonnambula, par une "
                  "compagnie itinérante (1850).\n\nLa première salle date de 1865, "
                  "détruite par le Great Fire de 1871. S'ensuivit le Chicago "
                  "Auditorium en 1889 (il ferme en 1941).",
             "img": [i("FuAL5LVWcAIhi8a.jpg"), i("FuAL8rJXoAAiBhf.jpg")]},
            {"t": "Le bâtiment actuel, le Civic Opera House, est inauguré en 1929, "
                  "grand building Art Déco conçu par des architectes qui ont aussi "
                  "bâti beaucoup de murs environnants.\n\nSa salle est la seconde "
                  "plus grande jauge lyrique des États-Unis (après le Met de New "
                  "York), dans les 3500 places.",
             "img": [i("FuAM5tPXoAAAR4z.jpg")]},
            {"t": "La compagnie fait immédiatement faillite avec la Grande "
                  "Dépression.\n\nEn 1954 (la précédente compagnie s'était "
                  "débandée en 1946), création de la compagnie actuelle avec une "
                  "saison incluant les débuts américains de Callas en Norma.",
             "img": [i("FuANne7X0AAfkbH.jpg")]},
            {"t": "Parmi les figures marquantes, le cofondateur de la compagnie, "
                  "Nicola Rescigno, chef (pas spécialement fabuleux) associé à "
                  "plusieurs témoignages de Callas (Il Pirata, Traviata et Médée à "
                  "Covent Garden, Médée à Dallas…).\n\nEt Bruno Bartoletti, "
                  "directeur musical de 1964 à… 2000 !",
             "img": [i("FuAOetoXsAUc1a5.jpg")]},
            {"t": "Sinon, c'est évidemment une grosse maison, celle où Noureïev, "
                  "Solti, Dohnányi, Moffo ont fait leurs débuts américains à "
                  "l'opéra, qui a laissé très peu de témoignages discographiques "
                  "cependant.",
             "img": [i("FuAPGVQWcAIZ2Z4.jpg")]},
            {"t": "L'inauguration du bâtiment eut lieu en 1929 avec l'œuvre d'un "
                  "compositeur de 28 ans (/Camille/, de Hamilton Forrest), jamais "
                  "reprise !\n\n(Pas un gros succès du tout.)",
             "img": [i("FuAPRByXgAAVBq5.jpg")]},
        ],
    },
    {
        "date": "2023-04-20",
        "lieu": "l'ENS Paris-Saclay",
        "oeuvre": "Violet",
        "compositeur": "Tom Coult",
        "blocs": [
            {"t": "🔵 Ce 20 avril 2023 (ainsi qu'hier et demain), la Scène de "
                  "Recherche de l'ENS Paris-Saclay donne /Violet/ de Tom Coult, un "
                  "opéra autour de la catastrophe (écologique ?) finale.\n\n"
                  "(Compte rendu détaillé dans un fil distinct : "
                  "https://x.com/carnetsol/status/1648941266434924544 )"},
        ],
    },
    {
        "date": "2023-08-06",
        "lieu": "Bourgas",
        "oeuvre": "Pinocchio",
        "compositeur": "Alexander Yosifov",
        "blocs": [
            {"t": "🔵 Ce 6 août 2023, on donnait :\n\n"
                  "*Pinocchio*\n\nd'**Alexander Yosifov** (1940-2016)"
                  "\n\nà l'Opéra d'État de "
                  "Bourgas.\n\nUn des nombreux cas d'opéras écrits pour les "
                  "enfants à l'Est de l'Europe, où la pratique est répandue "
                  "(République Tchèque et Russie, notamment).",
             "img": [i("F261wmjWgAAUA-n.png")]},
            {"t": "Je vous fais grâce de l'histoire.\n\nYossifov (apparemment, "
                  "c'est la translittération usuelle, même en anglais) était un "
                  "compositeur bulgare, élève de mon cher Vladigerov (pour ce "
                  "dernier, foncez sur la vaste anthologie Capriccio, c'est "
                  "tellement généreux et bien écrit)."},
            {"t": "Je n'ai pas pu entendre son Pinocchio, mais on trouve en ligne "
                  "plusieurs concertos, dans un goût très tonal, peut-être plus "
                  "marqué par le néoclassicisme et le jazz que le postromantisme "
                  "comme son maître.\n\nTrès accessible et plutôt bien fait en "
                  "tout cas !",
             "yt": ["pTZ4C8lBH7M"]},
            {"t": "Bourgas située sur une petite péninsule sur la Mer Noire, "
                  "200.000 habitants aujourd'hui.\n\nSi l'on passe l'attentat-"
                  "suicide de 2012 (du Hezbollah sur un car d'Israéliens), le lieu "
                  "est désormais plutôt connu comme lieu de villégiature "
                  "touristique :",
             "img": [i("F264-7fX0AACWOL.jpg")]},
            {"t": "hivers enneigés mais étés méditerranéens.\n\nL'agglomération a "
                  "contenu de nombreux ports de pêche, avant de devenir "
                  "principalement, à l'ère industrielle, un centre important de "
                  "l'industrie chimique (transformation des huiles !) et, "
                  "alentour, minier – mines de sel et de fer.",
             "img": [i("F265zF1XgAAlkA8.jpg")]},
            {"t": "La compagnie est fondée en 1947 (Opéra, Ballet, orchestre "
                  "philharmonique) – j'ai l'impression que c'est le même orchestre "
                  "qui joue les productions à l'Opéra et les concerts à la "
                  "Philharmonie.\n\nJ'aime beaucoup l'architecture très originale "
                  "du lieu.",
             "img": [i("F266V2ZXQAAHqjl.png")]},
        ],
    },
]


# ---------------------------------------------------------------------------
# Téléchargement des médias
# ---------------------------------------------------------------------------

def telecharger(url, destination):
    import urllib.request
    if os.path.exists(destination):
        return True
    requete = urllib.request.Request(
        url, headers={"User-Agent": "Mozilla/5.0 (carnetsol import)"})
    try:
        with urllib.request.urlopen(requete, timeout=45) as reponse:
            donnees = reponse.read()
        os.makedirs(os.path.dirname(destination), exist_ok=True)
        with open(destination, "wb") as fh:
            fh.write(donnees)
        return True
    except Exception as err:
        print("  !! échec %s (%s)" % (os.path.basename(destination), err),
              file=sys.stderr)
        return False


def rapatrier(url, date_str, compteur, racine, distant):
    """Renvoie l'adresse à écrire dans la notule."""
    if distant:
        return url
    extension = os.path.splitext(url.split("?")[0])[1] or ".jpg"
    nom = "%s-%02d%s" % (date_str.replace("-", ""), compteur, extension)
    chemin = os.path.join(racine, DOSSIER_MEDIAS, nom)
    if telecharger(url, chemin):
        return "%s/%s" % (PREFIXE_MEDIAS, nom)
    return url  # repli : on garde l'adresse Twitter plutôt que rien


# ---------------------------------------------------------------------------
# Fabrication du corps HTML
# ---------------------------------------------------------------------------

def construire_corps(journee, racine, distant):
    date_str = journee["date"]
    morceaux = []
    compteur = [0]

    def suivant():
        compteur[0] += 1
        return compteur[0]

    for bloc in journee["blocs"]:
        if bloc.get("t"):
            for paragraphe in bloc["t"].split("\n\n"):
                paragraphe = paragraphe.strip()
                if paragraphe:
                    morceaux.append("<p>%s</p>"
                                    % enrichir(paragraphe).replace("\n", "<br />"))
        for url in bloc.get("img", []):
            adresse = rapatrier(url, date_str, suivant(), racine, distant)
            morceaux.append(
                '<figure class="illustration">'
                '<img src="%s" alt="" loading="lazy" /></figure>' % adresse)
        for url in bloc.get("vid", []):
            adresse = rapatrier(url, date_str, suivant(), racine, distant)
            morceaux.append(
                '<figure class="illustration">'
                '<video src="%s" controls loop playsinline '
                'preload="none"></video></figure>' % adresse)
        for ident in bloc.get("yt", []):
            morceaux.append(
                '<figure class="video"><iframe width="560" height="315" '
                'src="https://www.youtube-nocookie.com/embed/%s" '
                'title="Extrait vidéo" frameborder="0" loading="lazy" '
                'allow="accelerometer; autoplay; clipboard-write; '
                'encrypted-media; gyroscope; picture-in-picture" '
                'allowfullscreen></iframe></figure>' % ident)

    return "\n".join(morceaux)


def construire_titre(journee, d):
    """Modèle repris du WordPress : « JJ/MM/AA : Nom, Œuvre (à Ville) »."""
    if journee.get("titre_force"):
        return journee["titre_force"]
    # le fil donne le prénom, le modèle ne garde que le patronyme
    nom = journee["compositeur"].split()[-1]
    return "%s : %s, %s (à %s)" % (d.strftime("%d/%m/%y"), nom,
                                   journee["oeuvre"], journee["lieu"])


# ---------------------------------------------------------------------------

def trouver_slug_categorie(racine):
    chemin = os.path.join(racine, "src", "content", "categories.json")
    try:
        with open(chemin, encoding="utf-8") as fh:
            categories = json.load(fh)
    except Exception:
        print("  (categories.json illisible : slug par défaut « %s »)"
              % CATEGORIE_SLUG_DEFAUT, file=sys.stderr)
        return CATEGORIE_SLUG_DEFAUT

    cible = slugifier(CATEGORIE_NOM)
    for cat in categories:
        nom = cat.get("nom", "")
        if slugifier(nom) == cible or "jour" in nom.lower() and "opera" in slugifier(nom):
            print("  catégorie trouvée : « %s » -> %s" % (nom, cat["slug"]),
                  file=sys.stderr)
            return cat["slug"]

    print("  !! catégorie « %s » absente de categories.json — "
          "slug « %s » utilisé, PENSEZ À L'AJOUTER"
          % (CATEGORIE_NOM, CATEGORIE_SLUG_DEFAUT), file=sys.stderr)
    return CATEGORIE_SLUG_DEFAUT


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--racine", default=".",
                    help="racine du projet Astro (défaut : dossier courant)")
    ap.add_argument("--ecrire", action="store_true",
                    help="écrit réellement les fichiers (sinon : simulation)")
    ap.add_argument("--distant", action="store_true",
                    help="garde les adresses pbs.twimg.com au lieu de rapatrier")
    ap.add_argument("--postid-depart", type=int, default=POSTID_DEPART)
    args = ap.parse_args()

    racine = args.racine
    dossier_notules = os.path.join(racine, "src", "content", "notules")
    if args.ecrire and not os.path.isdir(dossier_notules):
        sys.exit("Dossier introuvable : %s\n"
                 "Lancez le script depuis la racine du projet Astro." % dossier_notules)

    slug_categorie = trouver_slug_categorie(racine)
    categories = [{"nom": CATEGORIE_NOM, "slug": slug_categorie}]

    # adresses ET identifiants déjà pris : on ne doit jamais réattribuer un
    # postId. Deux notules partageant un identifiant, c'est une page qui
    # disparaît en silence au build (déduplication dans [...permalien].astro).
    urls_prises = set()
    ids_pris = set()
    if os.path.isdir(dossier_notules):
        for nom in os.listdir(dossier_notules):
            if nom.endswith(".json"):
                try:
                    with open(os.path.join(dossier_notules, nom),
                              encoding="utf-8") as fh:
                        donnees = json.load(fh)
                    urls_prises.add(donnees.get("url", ""))
                    ids_pris.add(int(donnees.get("postId", -1)))
                except Exception:
                    pass

    # on glisse jusqu'au premier identifiant libre de la plage demandée
    depart = args.postid_depart
    while depart in ids_pris:
        depart += 1
    if depart != args.postid_depart:
        print("  identifiants %d..%d déjà pris — démarrage à %d"
              % (args.postid_depart, depart - 1, depart), file=sys.stderr)

    lignes = []
    ecrits = 0
    postid = depart

    for journee in JOURNEES:
        d = datetime.strptime(journee["date"], "%Y-%m-%d")
        titre = construire_titre(journee, d)
        slug = slugifier("%s-%s-%s" % (journee["lieu"], journee["oeuvre"],
                                       journee["compositeur"]))[:70]

        corps = construire_corps(journee, racine, args.distant)

        entete = MARQUEUR.format(date_lisible=date_lisible(d), source=SOURCE_FIL)
        if journee.get("entete_manquant"):
            entete += MARQUEUR_ENTETE_MANQUANT
        if journee.get("date_douteuse"):
            entete += MARQUEUR_DATE_INCERTAINE.format(
                tel_quel=journee["date_douteuse"])
        corps = entete + corps

        url = "/css/%04d/%02d/%02d/%d-%s/" % (d.year, d.month, d.day, postid, slug)
        if url in urls_prises:
            url = url[:-1] + "-import/"
        urls_prises.add(url)
        ids_pris.add(postid)

        extrait = texte_seul(
            "\n".join(b.get("t", "") for b in journee["blocs"][:1]))[:300]

        notule = {
            "postId": postid,
            "titre": titre,
            "slug": slug,
            "url": url,
            "date": d.replace(hour=12).isoformat(),
            "modifie": None,
            "auteur": AUTEUR,
            "langue": "fr",
            "categories": categories,
            "chapoHtml": "",
            "corpsHtml": corps,
            "notesHtml": "",
            "extrait": extrait,
            "nbCommentaires": 0,
            "commentaires": [],
            "epingle": False,
            "importee": True,
            "source": SOURCE_FIL,
        }

        nom_fichier = "%s-%s-%s.json" % (PREFIXE_FICHIER,
                                         d.strftime("%Y%m%d"), slug[:50])
        chemin = os.path.join(dossier_notules, nom_fichier)

        drapeaux = []
        if journee.get("date_douteuse"):
            drapeaux.append("DATE À VÉRIFIER")
        if journee.get("entete_manquant"):
            drapeaux.append("EN-TÊTE RECONSTITUÉ")

        lignes.append("  [%d] %s — %s (%d caractères)%s"
                      % (postid, journee["date"], titre[:65], len(corps),
                         "  << " + " / ".join(drapeaux) if drapeaux else ""))

        if args.ecrire:
            if os.path.exists(chemin):
                print("  !! %s existe déjà — ignoré" % nom_fichier, file=sys.stderr)
            else:
                with open(chemin, "w", encoding="utf-8") as fh:
                    json.dump(notule, fh, ensure_ascii=False, indent=1)
                ecrits += 1

        postid += 1
        while postid in ids_pris:      # on saute tout numéro déjà utilisé
            postid += 1

    print("\nJournées trouvées dans le fil : %d" % len(JOURNEES))
    print("Catégorie : « %s » (%s)\n" % (CATEGORIE_NOM, slug_categorie))
    print("\n".join(lignes))

    if args.ecrire:
        print("\n%d notules écrites dans %s" % (ecrits, dossier_notules))
        if not args.distant:
            print("Médias rapatriés dans %s"
                  % os.path.join(racine, DOSSIER_MEDIAS))
    else:
        print("\n>>> SIMULATION — aucun fichier créé. "
              "Relancez avec --ecrire pour appliquer.")


if __name__ == "__main__":
    main()
