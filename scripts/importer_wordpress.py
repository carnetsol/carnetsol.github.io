# -*- coding: utf-8 -*-
"""
Importe un export WordPress (WXR) en notules autonomes pour Carnets sur sol.

Conçu pour carnetsol.wordpress.com (« Carnets sur sol (boueux) »), mais
utilisable pour les autres blogs : la catégorie et la plage d'identifiants
se règlent en ligne de commande.

Usage :
    python scripts\\importer_wordpress.py export.xml
    python scripts\\importer_wordpress.py export.xml --ecrire
    python scripts\\importer_wordpress.py export.xml --ecrire --brouillons

Les adresses d'images restent celles de WordPress : rien n'est téléchargé.
Un passage ultérieur pourra les rapatrier.

Zéro dépendance externe.
"""

import argparse
import html
import json
import os
import re
import sys
import unicodedata
import xml.etree.ElementTree as ET
from datetime import datetime

NS = {
    "wp": "http://wordpress.org/export/1.2/",
    "content": "http://purl.org/rss/1.0/modules/content/",
    "excerpt": "http://wordpress.org/export/1.2/excerpt/",
    "dc": "http://purl.org/dc/elements/1.1/",
}

CATEGORIE_DEFAUT = "Carnets sur sol (boueux)"
POSTID_DEFAUT = 94001          # 92000 = 1 jour 1 opéra, 93000 = disques
AUTEUR_DEFAUT = "DavidLeMarrec"
PREFIXE_FICHIER = "import-wp"

# Bandeau repris de la récupération du crash de 2025 (classe .recuperation).
BANDEAU_DEFAUT = "Initialement publié sur le site alternatif {blog}"

MARQUEUR = (
    '<p class="recuperation"><em>{bandeau}, le {date_lisible}. '
    '<a href="{lien}" rel="noopener">Version d\'origine</a>.</em></p>\n'
)

MOIS_FR = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet",
           "août", "septembre", "octobre", "novembre", "décembre"]


# ---------------------------------------------------------------------------
# Utilitaires
# ---------------------------------------------------------------------------

def slugifier(valeur):
    valeur = unicodedata.normalize("NFD", valeur or "")
    valeur = "".join(c for c in valeur if unicodedata.category(c) != "Mn")
    valeur = valeur.lower()
    valeur = re.sub(r"[^a-z0-9]+", "-", valeur)
    return re.sub(r"-{2,}", "-", valeur).strip("-") or "notule"


def texte_seul(fragment):
    fragment = re.sub(r"<[^>]+>", " ", fragment or "")
    return re.sub(r"\s+", " ", html.unescape(fragment)).strip()


def date_lisible(d):
    return "%d %s %d" % (d.day, MOIS_FR[d.month - 1], d.year)


def champ(item, nom):
    return item.findtext(nom, namespaces=NS) or ""


# ---------------------------------------------------------------------------
# Nettoyage du HTML Gutenberg
#
# WordPress enrobe chaque bloc de commentaires <!-- wp:… -->, colle des
# classes wp-block-* et des largeurs en pixels dans style=. Sur la mise en
# page Keepsake, ces largeurs fixes débordent : on les retire et on rend la
# main au CSS du site.
# ---------------------------------------------------------------------------

RE_COMMENTAIRE_BLOC = re.compile(r"<!--\s*/?wp:.*?-->", re.S)
RE_EMBED = re.compile(
    r'<figure class="wp-block-embed[^"]*"[^>]*>\s*'
    r'<div class="wp-block-embed__wrapper">\s*(.*?)\s*</div>\s*</figure>', re.S)
RE_YOUTUBE = re.compile(
    r"(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/embed/)([A-Za-z0-9_-]{11})")


def nettoyer_corps(brut, table_liens, blog_url):
    """Transforme le HTML WordPress en HTML sobre pour le site Astro."""
    texte = brut or ""

    # 1. intégrations : YouTube -> iframe ; renvoi interne -> lien
    def traiter_embed(m):
        url = html.unescape(m.group(1)).strip()
        yt = RE_YOUTUBE.search(url)
        if yt:
            return (
                '<figure class="video"><iframe width="560" height="315" '
                'src="https://www.youtube-nocookie.com/embed/%s" '
                'title="Extrait vidéo" frameborder="0" loading="lazy" '
                'allow="accelerometer; autoplay; clipboard-write; '
                'encrypted-media; gyroscope; picture-in-picture" '
                "allowfullscreen></iframe></figure>" % yt.group(1))
        cible = table_liens.get(url.rstrip("/") + "/", url)
        return ('<p class="renvoi">→ <a href="%s">%s</a></p>'
                % (cible, html.escape(url)))

    texte = RE_EMBED.sub(traiter_embed, texte)

    # 2. commentaires de blocs
    texte = RE_COMMENTAIRE_BLOC.sub("", texte)

    # 3. les largeurs choisies dans l'article sont conservées telles quelles :
    #    le débordement est traité par un max-width dans style.css, qui prime
    #    sur un width en ligne sans avoir à le retirer.

    # 4. classes WordPress -> classes du site
    def traiter_classe(m):
        classes = m.group(1).split()
        gardees = []
        if "wp-block-image" in classes or "wp-block-gallery" in classes:
            gardees.append("illustration")
        for c in classes:
            if c in ("alignleft", "alignright", "aligncenter"):
                gardees.append(c)
        if "wp-element-caption" in classes:
            gardees.append("legende")
        return ' class="%s"' % " ".join(gardees) if gardees else ""

    texte = re.sub(r'\s*class="([^"]*)"', traiter_classe, texte)

    # 5. chargement différé des images (1 400 images, sinon la page rame)
    texte = re.sub(r"<img (?![^>]*loading=)", '<img loading="lazy" ', texte)

    # 6. liens internes au blog -> nouvelles adresses du site
    for ancienne, nouvelle in table_liens.items():
        texte = texte.replace(ancienne, nouvelle)
        texte = texte.replace(ancienne.rstrip("/"), nouvelle)

    # 7. galeries imbriquées : on aplatit, le CSS du site s'en charge
    texte = re.sub(r'<figure class="illustration"(?=[^>]*>\s*<figure)', "<div", texte)

    # 8. blancs superflus
    texte = re.sub(r"\n{3,}", "\n\n", texte)
    return texte.strip()


# ---------------------------------------------------------------------------
# Catégories
# ---------------------------------------------------------------------------

def assurer_categorie(racine, nom, ecrire):
    """Renvoie le slug de la catégorie, en la créant ou la réparant au besoin.

    La collection « categories » impose un id NUMÉRIQUE (z.coerce.number()) :
    une chaîne vide fait échouer la compilation de tout le site. On calcule
    donc un identifiant libre, et on répare une entrée déjà écrite qui en
    manquerait.
    """
    chemin = os.path.join(racine, "src", "content", "categories.json")
    slug = slugifier(nom)
    try:
        with open(chemin, encoding="utf-8") as fh:
            categories = json.load(fh)
    except Exception as err:
        print("  !! categories.json illisible (%s) — slug « %s » supposé"
              % (err, slug), file=sys.stderr)
        return slug

    def entier(valeur, defaut=0):
        try:
            return int(valeur)
        except (TypeError, ValueError):
            return defaut

    ids = [entier(c.get("id"), 0) for c in categories]
    ordres = [entier(c.get("ordre"), 0) for c in categories]
    id_libre = max(ids) + 1 if ids else 1
    ordre_libre = max(ordres) + 1 if ordres else 1

    for cat in categories:
        if slugifier(cat.get("nom", "")) == slug or cat.get("slug") == slug:
            manques = []
            if not isinstance(cat.get("id"), int) or entier(cat.get("id"), 0) <= 0:
                cat["id"] = id_libre
                manques.append("id")
            if not isinstance(cat.get("ordre"), int):
                cat["ordre"] = ordre_libre
                manques.append("ordre")
            if not isinstance(cat.get("description"), str):
                cat["description"] = ""
                manques.append("description")
            if not cat.get("slug"):
                cat["slug"] = slug
                manques.append("slug")
            if manques:
                if ecrire:
                    with open(chemin, "w", encoding="utf-8") as fh:
                        json.dump(categories, fh, ensure_ascii=False, indent=1)
                    print("  catégorie RÉPARÉE : « %s » (%s)"
                          % (cat.get("nom", nom), ", ".join(manques)),
                          file=sys.stderr)
                else:
                    print("  catégorie À RÉPARER : « %s » (%s manquant)"
                          % (cat.get("nom", nom), ", ".join(manques)),
                          file=sys.stderr)
            else:
                print("  catégorie déjà présente : « %s » -> %s"
                      % (cat["nom"], cat["slug"]), file=sys.stderr)
            return cat["slug"]

    categories.append({
        "id": id_libre,
        "nom": nom,
        "description": "",
        "slug": slug,
        "ordre": ordre_libre,
    })

    if ecrire:
        with open(chemin, "w", encoding="utf-8") as fh:
            json.dump(categories, fh, ensure_ascii=False, indent=1)
        print("  catégorie CRÉÉE : « %s » -> %s (id %d)"
              % (nom, slug, id_libre), file=sys.stderr)
    else:
        print("  catégorie À CRÉER : « %s » -> %s (id %d, simulation)"
              % (nom, slug, id_libre), file=sys.stderr)
    return slug


# ---------------------------------------------------------------------------

def lire_commentaires(item):
    sortie = []
    for c in item.findall("wp:comment", NS):
        if (c.findtext("wp:comment_approved", namespaces=NS) or "") != "1":
            continue
        if (c.findtext("wp:comment_type", namespaces=NS) or "") not in ("", "comment"):
            continue
        brut = c.findtext("wp:comment_date", namespaces=NS) or ""
        try:
            quand = datetime.strptime(brut, "%Y-%m-%d %H:%M:%S").isoformat()
        except ValueError:
            quand = None
        sortie.append({
            "id": int(c.findtext("wp:comment_id", namespaces=NS) or 0),
            "auteur": c.findtext("wp:comment_author", namespaces=NS) or "Anonyme",
            "site": c.findtext("wp:comment_author_url", namespaces=NS) or "",
            "date": quand,
            # quote=False : dans du texte courant, échapper les apostrophes
            # en &#x27; alourdit le HTML sans rien protéger.
            "contenu": "<p>%s</p>" % html.escape(
                c.findtext("wp:comment_content", namespaces=NS) or "",
                quote=False,
            ).replace("\n\n", "</p><p>").replace("\n", "<br />"),
        })
    return sortie


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("export", help="fichier .xml exporté depuis WordPress")
    ap.add_argument("--racine", default=".")
    ap.add_argument("--ecrire", action="store_true")
    ap.add_argument("--brouillons", action="store_true",
                    help="importe aussi les billets non publiés")
    ap.add_argument("--categorie", default=CATEGORIE_DEFAUT)
    ap.add_argument("--postid-depart", type=int, default=POSTID_DEFAUT)
    ap.add_argument("--auteur", default=AUTEUR_DEFAUT)
    ap.add_argument("--categorie-plus", action="append", default=[],
                    metavar="NOM",
                    help="catégorie thématique ajoutée à toutes les notules "
                         "de cet import ; répétable")
    ap.add_argument("--categorie-periode", action="append", default=[],
                    metavar="DEBUT:FIN=NOM",
                    help="catégorie ajoutée aux seules notules dont la date "
                         "tombe entre DEBUT et FIN inclus (AAAA-MM-JJ) ; "
                         "sert aux saisons musicales. Répétable.")
    ap.add_argument("--seulement", default=None,
                    help="n'importe que les billets de ces jours "
                         "(AAAA-MM-JJ, séparés par des virgules) ; sert à "
                         "récupérer des billets d'une vieille sauvegarde")
    ap.add_argument("--forcer-doublons", action="store_true",
                    help="importe même les billets dont la date est déjà "
                         "occupée par une notule de la même catégorie")
    ap.add_argument("--bandeau", default=None,
                    help="phrase du bandeau ; {blog} est remplacé par le titre "
                         "du blog (défaut : « %s »)" % BANDEAU_DEFAUT)
    args = ap.parse_args()

    racine = args.racine
    dossier = os.path.join(racine, "src", "content", "notules")
    if args.ecrire and not os.path.isdir(dossier):
        sys.exit("Dossier introuvable : %s\n"
                 "Lancez le script depuis la racine du projet Astro." % dossier)

    arbre = ET.parse(args.export)
    canal = arbre.getroot().find("channel")
    blog_titre = canal.findtext("title") or "WordPress"
    blog_url = (canal.findtext("link") or "").rstrip("/")

    billets = [i for i in canal.findall("item")
               if champ(i, "wp:post_type") == "post"]
    etats = ("publish", "draft", "pending", "private") if args.brouillons \
        else ("publish",)
    retenus = [b for b in billets if champ(b, "wp:status") in etats]

    if args.seulement:
        voulus = {j.strip() for j in args.seulement.split(",") if j.strip()}
        avant = len(retenus)
        retenus = [b for b in retenus
                   if champ(b, "wp:post_date")[:10] in voulus]
        print("  --seulement : %d billet(s) retenu(s) sur %d"
              % (len(retenus), avant), file=sys.stderr)
        introuvables = voulus - {champ(b, "wp:post_date")[:10] for b in retenus}
        if introuvables:
            print("  !! aucun billet publié à ces dates : %s"
                  % ", ".join(sorted(introuvables)), file=sys.stderr)
    retenus.sort(key=lambda b: champ(b, "wp:post_date"))

    bandeau = (args.bandeau or BANDEAU_DEFAUT).format(blog=blog_titre)

    ecartes = len(billets) - len(retenus)
    slug_cat = assurer_categorie(racine, args.categorie, args.ecrire)
    categories = [{"nom": args.categorie, "slug": slug_cat}]

    # catégories thématiques valables pour tout l'import
    for nom in args.categorie_plus:
        categories.append({"nom": nom,
                           "slug": assurer_categorie(racine, nom, args.ecrire)})

    # catégories bornées dans le temps (saisons musicales)
    periodes = []
    for regle in args.categorie_periode:
        try:
            bornes, nom = regle.split("=", 1)
            debut, fin = bornes.split(":", 1)
            datetime.strptime(debut, "%Y-%m-%d")
            datetime.strptime(fin, "%Y-%m-%d")
        except ValueError:
            sys.exit("--categorie-periode mal formé : %s\n"
                     "Attendu : AAAA-MM-JJ:AAAA-MM-JJ=Nom de la catégorie"
                     % regle)
        periodes.append((debut, fin,
                         {"nom": nom,
                          "slug": assurer_categorie(racine, nom, args.ecrire)}))

    # identifiants et adresses déjà pris
    urls_prises, ids_pris, jours_pris = set(), set(), set()
    if os.path.isdir(dossier):
        for nom in os.listdir(dossier):
            if nom.endswith(".json"):
                try:
                    with open(os.path.join(dossier, nom), encoding="utf-8") as fh:
                        d = json.load(fh)
                    urls_prises.add(d.get("url", ""))
                    ids_pris.add(int(d.get("postId", -1)))
                    # un même jour dans une même catégorie = doublon probable
                    jour = str(d.get("date", ""))[:10]
                    for c in d.get("categories", []):
                        jours_pris.add((jour, c.get("slug", "")))
                except Exception:
                    pass

    depart = args.postid_depart
    while depart in ids_pris:
        depart += 1
    if depart != args.postid_depart:
        print("  identifiants %d.. déjà pris — démarrage à %d"
              % (args.postid_depart, depart), file=sys.stderr)

    # première passe : table de correspondance des liens internes
    table_liens, plan, doublons = {}, [], []
    postid = depart
    for billet in retenus:
        brut = champ(billet, "wp:post_date")
        try:
            d = datetime.strptime(brut, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            print("  !! date illisible (%s) — billet ignoré : %s"
                  % (brut, billet.findtext("title")), file=sys.stderr)
            continue
        if (d.strftime("%Y-%m-%d"), slug_cat) in jours_pris \
                and not args.forcer_doublons:
            doublons.append("  %s — %s" % (d.strftime("%Y-%m-%d"),
                                           (billet.findtext("title") or "")[:60]))
            continue
        slug = slugifier(champ(billet, "wp:post_name")
                         or billet.findtext("title") or "")[:70]
        url = "/css/%04d/%02d/%02d/%d-%s/" % (d.year, d.month, d.day, postid, slug)
        while url in urls_prises:
            url = url[:-1] + "-bis/"
        urls_prises.add(url)
        lien = (billet.findtext("link") or "").strip()
        if lien:
            table_liens[lien.rstrip("/") + "/"] = url
        plan.append((billet, d, slug, url, postid, lien))
        postid += 1
        while postid in ids_pris:
            postid += 1

    # seconde passe : fabrication
    lignes, ecrits, total_img = [], 0, 0
    for billet, d, slug, url, pid, lien in plan:
        titre = html.unescape(billet.findtext("title") or "Sans titre").strip()
        corps = nettoyer_corps(champ(billet, "content:encoded"),
                               table_liens, blog_url)
        entete = MARQUEUR.format(bandeau=html.escape(bandeau),
                                 date_lisible=date_lisible(d),
                                 lien=html.escape(lien or blog_url))
        corps = entete + corps

        extrait = texte_seul(champ(billet, "excerpt:encoded")) \
            or texte_seul(champ(billet, "content:encoded"))[:300]
        commentaires = lire_commentaires(billet)
        nb_img = len(re.findall(r"<img", corps))
        total_img += nb_img
        statut = champ(billet, "wp:status")

        cats_notule = list(categories)
        jour = d.strftime("%Y-%m-%d")
        for debut, fin, cat in periodes:
            if debut <= jour <= fin:
                cats_notule.append(cat)

        notule = {
            "postId": pid,
            "titre": titre,
            "slug": slug,
            "url": url,
            "date": d.isoformat(),
            "modifie": None,
            "auteur": args.auteur,
            "langue": "fr",
            "categories": cats_notule,
            "chapoHtml": "",
            "corpsHtml": corps,
            "notesHtml": "",
            "extrait": extrait[:300],
            "nbCommentaires": len(commentaires),
            "commentaires": commentaires,
            "epingle": False,
            "importee": True,
            "source": lien or blog_url,
        }

        fichier = "%s-%s-%s.json" % (PREFIXE_FICHIER, d.strftime("%Y%m%d"),
                                     slug[:50])
        lignes.append("  [%d] %s — %-52s %5d car, %3d img%s"
                      % (pid, d.strftime("%Y-%m-%d"), titre[:52], len(corps),
                         nb_img, "  << BROUILLON" if statut != "publish" else ""))

        if args.ecrire:
            chemin = os.path.join(dossier, fichier)
            if os.path.exists(chemin):
                print("  !! %s existe déjà — ignoré" % fichier, file=sys.stderr)
            else:
                with open(chemin, "w", encoding="utf-8") as fh:
                    json.dump(notule, fh, ensure_ascii=False, indent=1)
                ecrits += 1

    print("\nBlog : %s (%s)" % (blog_titre, blog_url))
    print("Catégorie : « %s » (%s)" % (args.categorie, slug_cat))
    for c in categories[1:]:
        print("      +    « %s » (%s)" % (c["nom"], c["slug"]))
    for debut, fin, c in periodes:
        print("      +    « %s » du %s au %s" % (c["nom"], debut, fin))
    print("Bandeau  : %s" % bandeau)
    print("Billets retenus : %d   (non publiés écartés : %d)" % (len(plan), ecartes))
    if doublons:
        print("\nDOUBLONS ÉCARTÉS (jour déjà occupé dans cette catégorie) : %d"
              % len(doublons))
        print("\n".join(doublons))
        print("  → --forcer-doublons pour les importer quand même\n")
    else:
        print("")
    print("\n".join(lignes))
    print("\nImages (adresses WordPress conservées) : %d" % total_img)
    print("Liens internes réécrits : %d" % len(table_liens))

    if args.ecrire:
        print("\n%d notules écrites dans %s" % (ecrits, dossier))
    else:
        print("\n>>> SIMULATION — aucun fichier créé. "
              "Relancez avec --ecrire pour appliquer.")


if __name__ == "__main__":
    main()
