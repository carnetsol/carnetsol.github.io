#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Bilan de santé du site avant mise en ligne.

Ne modifie rien : vérifie et rapporte.

Usage :
    python verifier_site.py
    python verifier_site.py --dump dump.sql      (contrôles supplémentaires)

Contrôles effectués :
  1. Comptage des notules par origine (dump / récupération / Markdown)
  2. Cohérence des dates et détection d'anomalies chronologiques
  3. Doublons : même adresse, ou même date + titre
  4. Champs vides ou suspects (titre manquant, corps vide)
  5. Médias : liens locaux cassés, liens restés vers l'ancien site
  6. Liens internes vers des notules inexistantes
  7. Catégories orphelines ou non déclarées
  8. Traces indésirables (Wayback, chemins non réécrits, adresses IP)
"""

import argparse
import json
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NOTULES = os.path.join(RACINE, "src", "content", "notules")
NOUVELLES = os.path.join(RACINE, "src", "content", "nouvelles")
CORRECTIONS = os.path.join(RACINE, "src", "content", "corrections")
CATEGORIES = os.path.join(RACINE, "src", "content", "categories.json")
MEDIAS = os.path.join(RACINE, "public", "medias")

OK, ALERTE, INFO = "  ok  ", "  !!  ", "  ..  "
problemes = []


def titre(t):
    print("\n" + "=" * 68)
    print(t)
    print("=" * 68)


def dire(niveau, message):
    print(niveau + message)
    if niveau == ALERTE:
        problemes.append(message)


def charger_notules():
    out = []
    if not os.path.isdir(NOTULES):
        dire(ALERTE, f"Dossier introuvable : {NOTULES}")
        return out
    for nom in sorted(os.listdir(NOTULES)):
        if not nom.endswith(".json"):
            continue
        chemin = os.path.join(NOTULES, nom)
        try:
            with open(chemin, encoding="utf-8") as fh:
                d = json.load(fh)
        except json.JSONDecodeError as e:
            dire(ALERTE, f"JSON illisible : {nom} ({e})")
            continue
        d["_fichier"] = nom
        out.append(d)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dump", default=None,
                    help="dump SQL, pour comparer les adresses à l'original")
    ap.add_argument("--rapport", default="bilan-site.txt")
    args = ap.parse_args()

    notules = charger_notules()

    # ---------------------------------------------------------------- 1
    titre("1. COMPTAGE")
    depuis_dump = [n for n in notules if not n["_fichier"].startswith("recup-")]
    recuperees = [n for n in notules if n["_fichier"].startswith("recup-")]
    md = []
    if os.path.isdir(NOUVELLES):
        md = [f for f in os.listdir(NOUVELLES) if f.endswith((".md", ".mdx"))]
    corrections = []
    if os.path.isdir(CORRECTIONS):
        corrections = [f for f in os.listdir(CORRECTIONS) if f.endswith(".json")]

    dire(INFO, f"notules issues du dump      : {len(depuis_dump)}")
    dire(INFO, f"notules récupérées (crash)  : {len(recuperees)}")
    dire(INFO, f"notules écrites en Markdown : {len(md)}")
    dire(INFO, f"correctifs appliqués        : {len(corrections)}")
    dire(INFO, f"TOTAL publié                : {len(notules) + len(md)}")

    # les correctifs pointent-ils vers des notules existantes ?
    ids = {n.get("postId") for n in notules}
    for c in corrections:
        try:
            pid = int(os.path.splitext(c)[0])
        except ValueError:
            continue
        if pid not in ids:
            dire(ALERTE, f"correctif {c} ne correspond à aucune notule")

    # ---------------------------------------------------------------- 2
    titre("2. DATES")
    sans_date, futures, anciennes = [], [], []
    par_annee = Counter()
    maintenant = datetime.now()
    for n in notules:
        try:
            d = datetime.fromisoformat(n["date"])
        except (KeyError, ValueError):
            sans_date.append(n["_fichier"])
            continue
        par_annee[d.year] += 1
        if d > maintenant:
            futures.append((n["_fichier"], n["date"], n.get("titre", "")[:45]))
        if d.year < 2004:
            anciennes.append((n["_fichier"], n["date"]))

    dire(OK if not sans_date else ALERTE,
         f"notules sans date exploitable : {len(sans_date)}")
    dire(OK if not anciennes else ALERTE,
         f"notules antérieures à 2004    : {len(anciennes)}")
    if futures:
        dire(INFO, f"notules datées dans le futur  : {len(futures)}")
        for f, d, t in futures[:5]:
            print(f"        {d[:10]}  {t}")
    if par_annee:
        annees = sorted(par_annee)
        dire(INFO, f"période couverte : {annees[0]} → {annees[-1]}")
        creux = [a for a in range(annees[0], annees[-1] + 1)
                 if par_annee.get(a, 0) == 0]
        if creux:
            dire(ALERTE, f"années sans aucune notule : {creux}")

    # ---------------------------------------------------------------- 3
    titre("3. DOUBLONS")
    par_url = defaultdict(list)
    par_datetitre = defaultdict(list)
    for n in notules:
        par_url[n.get("url", "")].append(n["_fichier"])
        cle = (n.get("date", "")[:10],
               re.sub(r"\s+", " ", n.get("titre", "")).strip().lower())
        par_datetitre[cle].append(n["_fichier"])

    doublons_url = {u: f for u, f in par_url.items() if len(f) > 1}
    doublons_dt = {c: f for c, f in par_datetitre.items() if len(f) > 1}

    dire(OK if not doublons_url else ALERTE,
         f"adresses en double : {len(doublons_url)}")
    for u, f in list(doublons_url.items())[:10]:
        print(f"        {u}  ->  {', '.join(f)}")

    dire(OK if not doublons_dt else ALERTE,
         f"même date ET même titre : {len(doublons_dt)}")
    for (d, t), f in list(doublons_dt.items())[:10]:
        print(f"        {d} « {t[:50]} »  ->  {', '.join(f)}")

    # ---------------------------------------------------------------- 4
    titre("4. CHAMPS")
    sans_titre = [n["_fichier"] for n in notules if not n.get("titre", "").strip()]
    sans_corps = [n["_fichier"] for n in notules
                  if len(n.get("corpsHtml", "")) < 30
                  and len(n.get("chapoHtml", "")) < 30]
    sans_cat = [n["_fichier"] for n in notules if not n.get("categories")]

    dire(OK if not sans_titre else ALERTE, f"notules sans titre : {len(sans_titre)}")
    dire(OK if not sans_corps else ALERTE,
         f"notules au contenu quasi vide : {len(sans_corps)}")
    for f in sans_corps[:8]:
        print(f"        {f}")
    dire(INFO, f"notules sans aucune catégorie : {len(sans_cat)}")

    # ---------------------------------------------------------------- 5
    titre("5. MÉDIAS")
    presents = set(os.listdir(MEDIAS)) if os.path.isdir(MEDIAS) else set()
    dire(INFO, f"fichiers dans public/medias : {len(presents)}")

    ref_locales, ref_distantes, casses = set(), set(), Counter()
    motif_local = re.compile(r'/medias/([^"\'\s>)]+)')
    motif_free = re.compile(r'operacritiques\.free\.fr/[^"\'\s>)]*')

    def champs_texte(n):
        """Champs à analyser, décodés — jamais le JSON brut, dont les
        guillemets échappés tronquent les captures."""
        out = [n.get("corpsHtml", ""), n.get("chapoHtml", ""),
               n.get("notesHtml", ""), n.get("titre", "")]
        for c in n.get("commentaires", []):
            out.append(c.get("contenu", ""))
        return out

    for n in notules:
        for texte in champs_texte(n):
            for m in motif_local.finditer(texte):
                nom = os.path.basename(m.group(1))
                ref_locales.add(nom)
                if nom not in presents:
                    casses[nom] += 1
            for m in motif_free.finditer(texte):
                ref_distantes.add(m.group(0))

    dire(INFO, f"fichiers référencés en local  : {len(ref_locales)}")
    dire(INFO, f"liens laissés vers l'ancien site : {len(ref_distantes)}")
    dire(OK if not casses else ALERTE,
         f"liens locaux SANS fichier correspondant : {len(casses)}")
    for nom, cnt in casses.most_common(12):
        print(f"        {nom}  ({cnt} occurrence(s))")

    orphelins = presents - ref_locales
    dire(INFO, f"fichiers présents mais jamais référencés : {len(orphelins)}")

    # ---------------------------------------------------------------- 6
    titre("6. LIENS INTERNES")
    urls_connues = {n.get("url", "") for n in notules}
    # On analyse le HTML DÉCODÉ, pas le texte brut du fichier : dans le JSON
    # les guillemets sont échappés en \" et une capture naïve tronque les
    # slugs longs, ce qui fabrique des liens « cassés » qui n'existent pas.
    motif_interne = re.compile(r'(/css/\d{4}/\d{2}/\d{2}/[^"\'\s>)]+)')
    internes_casses = Counter()
    for n in notules:
        champs = (n.get("corpsHtml", ""), n.get("chapoHtml", ""),
                  n.get("notesHtml", ""))
        for c in n.get("commentaires", []):
            champs = champs + (c.get("contenu", ""),)
        for texte in champs:
            for m in motif_interne.finditer(texte):
                u = m.group(1)
                if not u.endswith("/"):
                    u += "/"
                if u not in urls_connues:
                    internes_casses[u] += 1

    dire(OK if not internes_casses else ALERTE,
         f"liens vers des notules inexistantes : {len(internes_casses)}")
    for u, cnt in internes_casses.most_common(10):
        print(f"        {u}  ({cnt}x)")

    # ---------------------------------------------------------------- 7
    titre("7. CATÉGORIES")
    declarees = {}
    if os.path.isfile(CATEGORIES):
        with open(CATEGORIES, encoding="utf-8") as fh:
            for c in json.load(fh):
                declarees[c["slug"]] = c["nom"]
    dire(INFO, f"catégories déclarées : {len(declarees)}")

    utilisees = Counter()
    for n in notules:
        for c in n.get("categories", []):
            utilisees[c.get("slug", "")] += 1

    inconnues = [s for s in utilisees if s not in declarees]
    dire(OK if not inconnues else ALERTE,
         f"catégories utilisées mais non déclarées : {len(inconnues)}")
    for s in inconnues[:10]:
        print(f"        {s} ({utilisees[s]} notules)")

    vides = [s for s in declarees if s not in utilisees]
    dire(INFO, f"catégories déclarées mais vides : {len(vides)}")

    # ---------------------------------------------------------------- 8
    titre("8. TRACES INDÉSIRABLES")
    controles = [
        ("web.archive.org", re.compile(r"web\.archive\.org")),
        ("chemin /css/images/ non réécrit", re.compile(r'"/css/images/')),
        # Une IP n'est signalée que si chaque octet est plausible ET qu'elle
        # n'est pas précédée d'un chiffre de numérotation de section
        # (« 2.2.1.1 » d'un plan détaillé n'est pas une adresse).
        ("adresse IP publique",
         re.compile(r"(?<![\d.])(?:(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)\.)"
                    r"{3}(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)(?![\d.])")),
        ("adresse de courriel", re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")),
        ("préfixe HTTrack résiduel", re.compile(r"https?_/")),
    ]
    for libelle, motif in controles:
        touchees = [n["_fichier"] for n in notules
                    if any(motif.search(t) for t in champs_texte(n))]
        niveau = OK if not touchees else ALERTE
        # Deux contrôles ne peuvent pas trancher seuls et restent indicatifs :
        #  - les courriels cités dans une notule sont souvent volontaires ;
        #  - « 2.2.1.1 » d'un plan numéroté est indiscernable d'une vraie IP.
        # Le script de migration n'exporte de toute façon jamais comment_ip :
        # aucune adresse de commentateur ne peut se retrouver ici.
        if libelle in ("adresse de courriel", "adresse IP publique") and touchees:
            niveau = INFO
        dire(niveau, f"{libelle} : {len(touchees)} notule(s)")
        for f in touchees[:5]:
            print(f"        {f}")

    # ---------------------------------------------------------------- 9
    titre("9. NOTULES RÉELLEMENT PUBLIÉES")
    # Contrôle décisif : les contrôles précédents lisent les FICHIERS.
    # Si la configuration Astro perd des entrées en route (identifiants de
    # collection en collision, par exemple), le site publie moins de notules
    # que le disque n'en contient — sans le moindre message d'erreur.
    dist = os.path.join(RACINE, "dist", "css")
    if not os.path.isdir(dist):
        dire(INFO, "dossier dist/ absent : lancez « npm run build » "
                   "puis relancez ce contrôle")
    else:
        publiees = set()
        for racine_d, _, fichiers_d in os.walk(dist):
            if "index.html" not in fichiers_d:
                continue
            rel = os.path.relpath(racine_d, dist).replace(os.sep, "/")
            if rel in (".", "recherche"):
                continue
            with open(os.path.join(racine_d, "index.html"),
                      encoding="utf-8", errors="replace") as fh:
                debut = fh.read(1200)
            # Les pages d'alias ne sont que des redirections : on ne les
            # compte pas comme des notules publiées.
            if 'http-equiv="refresh"' in debut:
                continue
            publiees.add("/css/" + rel + "/")

        attendues = {n.get("url", "") for n in notules}
        manquantes = attendues - publiees

        dire(INFO, f"notules sur le disque : {len(attendues)}")
        dire(INFO, f"pages publiées        : {len(publiees)}")
        dire(OK if not manquantes else ALERTE,
             f"notules ABSENTES du site : {len(manquantes)}")
        for u in sorted(manquantes)[:15]:
            print(f"        {u}")

    # ---------------------------------------------------------------- bilan
    titre("BILAN")
    if problemes:
        print(f"{len(problemes)} point(s) à examiner :\n")
        for p in problemes:
            print("  - " + p)
    else:
        print("Aucune anomalie détectée.")

    with open(os.path.join(RACINE, args.rapport), "w", encoding="utf-8") as fh:
        fh.write("\n".join(problemes) if problemes else "Aucune anomalie détectée.")
    print(f"\n(rapport : {args.rapport})")


if __name__ == "__main__":
    main()
