#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Migration Dotclear 1.2 (dump phpMyAdmin) -> collection de contenu Astro.

Usage :
    python3 scripts/migrate_dotclear.py dump.sql --out src/content

Produit :
    src/content/notules/<post_id>.json     une notule par fichier
    src/content/categories.json            l'arborescence des catégories
    src/content/commentaires/<post_id>.json (optionnel, --avec-commentaires)
    public/redirects.json                  table des anciennes URL -> nouvelles

Le script ne dépend d'aucun paquet externe : il tokenise directement les
instructions INSERT du dump, en respectant l'échappement MySQL. Il n'a donc
pas besoin qu'un serveur MySQL soit installé.
"""

import argparse
import html
import json
import os
import re
import sys
import unicodedata
from collections import defaultdict
from datetime import datetime

# --------------------------------------------------------------------------
# 1. Lecture du dump : tokeniseur d'INSERT
# --------------------------------------------------------------------------

ANOMALIES = []

INSERT_RE = re.compile(
    r"INSERT\s+INTO\s+`(?P<table>[^`]+)`\s*\((?P<cols>[^)]*)\)\s*VALUES\s*",
    re.IGNORECASE,
)

# Séquences d'échappement MySQL, cf. doc « String Literals »
UNESCAPE = {
    "0": "\0", "'": "'", '"': '"', "b": "\b", "n": "\n",
    "r": "\r", "t": "\t", "Z": "\x1a", "\\": "\\", "%": "\\%", "_": "\\_",
}


def parse_value_tuples(text, pos):
    """Lit la liste de tuples qui suit un VALUES, à partir de `pos`.

    Renvoie (liste_de_tuples, position_apres_le_point_virgule).
    Chaque tuple est une liste de valeurs Python (str, int, float ou None).
    """
    rows = []
    n = len(text)
    while pos < n:
        # sauter les blancs et les virgules entre tuples
        while pos < n and text[pos] in " \t\r\n,":
            pos += 1
        if pos >= n or text[pos] == ";":
            return rows, pos + 1
        if text[pos] != "(":
            # Instruction terminée ou format inattendu
            return rows, pos
        pos += 1
        row = []
        field = []
        is_string = False   # ce champ a-t-il été écrit entre quotes ?
        in_string = False   # sommes-nous actuellement à l'intérieur des quotes ?
        while pos < n:
            ch = text[pos]
            if in_string:
                if ch == "\\":
                    nxt = text[pos + 1] if pos + 1 < n else ""
                    field.append(UNESCAPE.get(nxt, nxt))
                    pos += 2
                    continue
                if ch == "'":
                    # '' à l'intérieur d'une chaîne = apostrophe littérale
                    if pos + 1 < n and text[pos + 1] == "'":
                        field.append("'")
                        pos += 2
                        continue
                    # Le dump contient des apostrophes NON échappées au milieu
                    # du texte, à deux titres :
                    #   « Un art de l'<em>atmosphère</em> »  (apostrophe de mot)
                    #   « (France, 1909, 9') »               (minutes d'un film)
                    # Une quote ne ferme donc la chaîne que si ce qui suit est
                    # vraiment un délimiteur : une virgule, ou une parenthèse
                    # fermante elle-même suivie d'une virgule / d'un point-virgule
                    # (fin de tuple). Une parenthèse au fil du texte, elle, est
                    # suivie d'autre chose et ne compte pas.
                    reste = text[pos + 1:pos + 60]
                    ferme = (
                        re.match(r"\s*,", reste)
                        or re.match(r"\s*\)\s*[,;]", reste)
                        or (pos + 1 >= n or re.match(r"\s*\)\s*$", reste))
                    )
                    if not ferme:
                        field.append("'")
                        pos += 1
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
                field = []      # jeter les blancs qui précèdent la quote
                pos += 1
                continue
            if ch == ",":
                row.append(finish_field(field, is_string))
                field = []
                is_string = False
                pos += 1
                continue
            if ch == ")":
                row.append(finish_field(field, is_string))
                pos += 1
                break
            field.append(ch)
            pos += 1
        rows.append(row)
    return rows, pos


def finish_field(chunks, is_string):
    raw = "".join(chunks)
    if is_string:
        return raw
    raw = raw.strip()
    if raw.upper() == "NULL" or raw == "":
        return None
    try:
        return int(raw)
    except ValueError:
        try:
            return float(raw)
        except ValueError:
            return raw


def read_tables(path, wanted):
    """Renvoie {table: [dict(colonne -> valeur), ...]} pour les tables voulues."""
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        text = fh.read()

    out = defaultdict(list)
    for m in INSERT_RE.finditer(text):
        table = m.group("table")
        if table not in wanted:
            continue
        cols = [c.strip().strip("`") for c in m.group("cols").split(",")]
        rows, _ = parse_value_tuples(text, m.end())
        for row in rows:
            if len(row) != len(cols):
                # Découpage incohérent : on le signale au lieu de l'ignorer.
                apercu = str(row[0])[:40] if row else "?"
                ANOMALIES.append(
                    f"{table} : ligne commençant par {apercu!r} découpée en "
                    f"{len(row)} champs au lieu de {len(cols)}"
                )
                continue
            out[table].append(dict(zip(cols, row)))
    return out


# --------------------------------------------------------------------------
# 2. Réparation d'encodage
# --------------------------------------------------------------------------

MOJIBAKE_HINTS = (
    "\u00c3\u00a9",  # é mal décodé
    "\u00c3\u00a8",  # è
    "\u00c3\u00aa",  # ê
    "\u00c3\u00a7",  # ç
    "\u00c3\u00b4",  # ô
    "\u00c3\u00bb",  # û
    "\u00e2\u0080\u0099",  # apostrophe typographique
    "\u00c5\u201c",  # œ
)


def fix_encoding(s):
    """Répare le cas classique « UTF-8 lu comme latin-1 » (Ã© au lieu de é).

    Les colonnes sont déclarées latin1 mais Dotclear y a écrit de l'UTF-8 ;
    selon la façon dont le dump a été produit, le texte peut ressortir
    doublement encodé. On ne corrige que si des marqueurs sont présents,
    pour ne pas abîmer le texte déjà correct.
    """
    if not isinstance(s, str) or not s:
        return s
    if not any(h in s for h in MOJIBAKE_HINTS):
        return s
    try:
        repaired = s.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return s
    # On ne garde la réparation que si elle réduit le nombre d'anomalies
    before = sum(s.count(h) for h in MOJIBAKE_HINTS)
    after = sum(repaired.count(h) for h in MOJIBAKE_HINTS)
    return repaired if after < before else s


# --------------------------------------------------------------------------
# 3. Nettoyage du corps HTML
# --------------------------------------------------------------------------

# Anciennes URL internes : index.php?2006/07/04/273-slug  ou  index.php?Categorie
# Dotclear résolvait une notule par son IDENTIFIANT : le slug qui suit était
# facultatif et pouvait être tronqué. Ces trois formes étaient équivalentes :
#   index.php?2013/04/04/2230-michelangelo-falvetti-le-deluge-universel
#   index.php?2013/04/04/2230-michelangelo-falvetti
#   index.php?2013/04/04/2230
# Le slug est donc optionnel dans l'expression, sans quoi la dernière forme
# n'était pas réécrite et devenait un lien mort.
OLD_POST_LINK = re.compile(
    r"https?://operacritiques\.free\.fr/(?:css|dotclear)/index\.php\?"
    r"(\d{4})/(\d{2})/(\d{2})/(\d+)(-[^\"'\s&#]*)?",
    re.IGNORECASE,
)
OLD_SEARCH_LINK = re.compile(
    r"https?://operacritiques\.free\.fr/(?:css|dotclear)/index\.php\?q=([^\"'\s&#]*)",
    re.IGNORECASE,
)
OLD_CAT_LINK = re.compile(
    r"https?://operacritiques\.free\.fr/(?:css|dotclear)/index\.php\?([A-Za-z][\w\-]*)",
    re.IGNORECASE,
)

# Fichiers médias hébergés sur l'ancien site (images, mais aussi sons/vidéos
# parfois déposés au même endroit). On capture le chemin après le domaine
# pour ne garder que le nom de fichier lors de la réécriture.
# Médias écrits en chemin relatif à la racine, sans nom de domaine :
#   <img src="/css/images/evgeny_kissin.jpg">
# Très fréquent dans le corpus, et invisible pour la règle sur les adresses
# absolues : sans cette seconde règle, ces images restent brisées.
# Le nom de fichier peut contenir des ESPACES (« Reger duos Klepper.jpg ») :
# on s'arrête au guillemet fermant, pas au premier blanc.
MEDIA_RACINE = re.compile(
    r"(?<=[\"'])/(?:css/)?(?:images|sons|documents)/"
    r"([^\"'>]+\.(?:jpe?g|png|gif|webp|svg|bmp|jfif|tiff?|mp3|mp4|pdf|ogg|m4a|flac|wav|avi|wmv|flv|mov|swf|mid|zip))(?=[\"'])",
    re.IGNORECASE,
)

OLD_MEDIA_LINK = re.compile(
    r"https?://operacritiques\.free\.fr/(?:css/)?(?:images|documents|files|media)?/?"
    r"([^\"'>]+\.(?:jpe?g|png|gif|webp|svg|bmp|jfif|tiff?|mp3|mp4|pdf|ogg|m4a|flac|wav|avi|wmv|flv|mov|swf|mid|zip))(?=[\"'\s>])",
    re.IGNORECASE,
)


# Types renvoyés vers un hébergement séparé quand --base-audio est fourni :
# ce sont eux qui pèsent (1132 mp3, 187 mp4) et qui dépassent les limites
# par fichier des hébergeurs statiques.
EXT_LOURDES = (".mp3", ".mp4", ".flac", ".wav", ".m4a", ".ogg",
               ".avi", ".wmv", ".flv", ".mov")


def rewrite_media_links(body, medias_dispo, medias_manquants, base_audio="",
                         garder_lourds_distants=False):
    """Réécrit images, sons et vidéos vers /medias/<nom de fichier>.

    Un seul dossier pour tous les types : le corpus mélange .jpg, .mp3 et .mp4
    dans les mêmes notules, et les répartir en plusieurs dossiers obligerait à
    trier des milliers de fichiers à la main pour aucun bénéfice.
    """
    def destination(nom_fichier):
        if base_audio and nom_fichier.lower().endswith(EXT_LOURDES):
            return base_audio.rstrip("/") + "/" + nom_fichier
        return "/medias/" + nom_fichier

    def sub(m):
        nom_fichier = os.path.basename(m.group(1))
        lourd = nom_fichier.lower().endswith(EXT_LOURDES)

        # Les gros fichiers (mp3, mp4, flac…) restent hébergés sur l'ancien
        # site : rien à copier, rien à indexer, aucune trace dans le rapport
        # de fichiers manquants. Le lien d'origine est laissé intact.
        if lourd and garder_lourds_distants and not base_audio:
            origine = m.group(0)
            # Un chemin relatif à la racine (« /css/images/x.mp3 ») ne veut
            # rien dire sur le nouveau domaine : on le rend absolu vers
            # l'ancien site, sinon le lecteur audio pointe dans le vide.
            if origine.startswith("/"):
                return "http://operacritiques.free.fr" + (
                    origine if origine.startswith("/css/")
                    else "/css" + origine)
            return origine

        if medias_dispo is not None:
            if nom_fichier in medias_dispo:
                return destination(nom_fichier)
            medias_manquants.add(nom_fichier)
            return m.group(0)  # lien d'origine conservé tant qu'on n'a pas le fichier
        return destination(nom_fichier)

    body = OLD_MEDIA_LINK.sub(sub, body)
    return MEDIA_RACINE.sub(sub, body)


def rewrite_internal_links(body, cat_urls):
    body = OLD_POST_LINK.sub(
        lambda m: "/css/%s/%s/%s/%s%s/" % (m.group(1), m.group(2), m.group(3),
                                          m.group(4), m.group(5) or ""),
        body,
    )
    body = OLD_SEARCH_LINK.sub(lambda m: "/css/recherche/?q=" + m.group(1), body)

    def cat_sub(m):
        slug = m.group(1)
        if slug.lower() in cat_urls:
            return "/css/categorie/%s/" % slug
        return m.group(0)

    return OLD_CAT_LINK.sub(cat_sub, body)


def strip_tags(s):
    return re.sub(r"<[^>]+>", " ", s or "")


def make_excerpt(chapo, content, limit=320):
    """Chapô si présent, sinon début du corps, en texte brut."""
    source = chapo if (chapo and strip_tags(chapo).strip()) else content
    text = html.unescape(strip_tags(source))
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= limit:
        return text
    cut = text[:limit]
    if " " in cut:
        cut = cut[: cut.rfind(" ")]
    return cut + "…"


def slugify(value):
    value = unicodedata.normalize("NFKD", value or "")
    value = value.encode("ascii", "ignore").decode("ascii")
    value = re.sub(r"[^\w\s-]", "", value).strip().lower()
    value = re.sub(r"[-\s]+", "-", value).strip("-")
    return value or "notule"


# --------------------------------------------------------------------------
# 4. Conversion
# --------------------------------------------------------------------------

def to_int(value, defaut=0):
    """Certains dumps phpMyAdmin écrivent les entiers entre quotes ('0').
    On force donc la conversion plutôt que de se fier au type détecté."""
    if value is None or value == "":
        return defaut
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return defaut


def to_datetime(value):
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(str(value), fmt)
        except ValueError:
            continue
    return None


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("dump", help="chemin du fichier .sql")
    ap.add_argument("--out", default="src/content", help="dossier de sortie")
    ap.add_argument("--public", default="public", help="dossier public (redirections)")
    ap.add_argument("--prefixe", default="sursol", help="préfixe des tables")
    ap.add_argument("--avec-commentaires", action="store_true",
                    help="exporter aussi les commentaires publiés")
    ap.add_argument("--brouillons", action="store_true",
                    help="inclure les notules non publiées")
    ap.add_argument("--garder-lourds-distants", dest="garder_lourds_distants",
                    action="store_true",
                    help="mp3/mp4/flac/wav/... restent liés vers l'ancien "
                         "site (operacritiques.free.fr) au lieu d'être "
                         "recherchés dans --medias. Rien n'est copié ni "
                         "indexé pour ces formats ; à combiner avec le "
                         "maintien de l'ancien hébergement en ligne.")
    ap.add_argument("--base-audio", dest="base_audio", default="",
                    help="adresse de base pour les fichiers audio/vidéo, "
                         "hébergés séparément du site "
                         "(ex. https://medias.carnetsol.fr). Sans cette option, "
                         "tout pointe vers /medias/")
    ap.add_argument("--medias", "--images", dest="medias", default=None,
                    help="dossier contenant les fichiers joints (images, mp3, "
                         "mp4, pdf). Il est parcouru récursivement, on peut donc "
                         "viser le dossier parent. Les liens vers l'ancien "
                         "serveur sont réécrits en /medias/<fichier>")
    args = ap.parse_args()

    p = args.prefixe
    wanted = {f"{p}_post", f"{p}_categorie", f"{p}_post_cat", f"{p}_comment"}
    print("Lecture du dump…", file=sys.stderr)
    tables = read_tables(args.dump, wanted)

    # --- catégories ---
    categories = {}
    for row in tables.get(f"{p}_categorie", []):
        cid = to_int(row["cat_id"])
        categories[cid] = {
            "id": to_int(cid),
            "nom": fix_encoding(row.get("cat_libelle") or ""),
            "description": fix_encoding(row.get("cat_desc") or ""),
            "slug": row.get("cat_libelle_url") or slugify(row.get("cat_libelle") or ""),
            "ordre": to_int(row.get("cat_ord"), 999),
        }
    cat_urls = {c["slug"].lower(): c for c in categories.values()}
    print(f"  {len(categories)} catégories", file=sys.stderr)

    # --- rattachements multiples ---
    post_cats = defaultdict(list)
    for row in tables.get(f"{p}_post_cat", []):
        post_cats[to_int(row["post_id"])].append(to_int(row["cat_id"]))

    # --- commentaires ---
    comments = defaultdict(list)
    if args.avec_commentaires:
        for row in tables.get(f"{p}_comment", []):
            if not to_int(row.get("comment_pub")):
                continue
            if to_int(row.get("comment_trackback")):
                continue
            dt = to_datetime(row.get("comment_dt"))
            comments[to_int(row["post_id"])].append({
                "id": to_int(row["comment_id"]),
                "auteur": fix_encoding(row.get("comment_auteur") or "Anonyme"),
                "site": row.get("comment_site") or "",
                "date": dt.isoformat() if dt else None,
                "contenu": fix_encoding(row.get("comment_content") or ""),
            })
        print(f"  {sum(len(v) for v in comments.values())} commentaires publiés",
              file=sys.stderr)

    # --- images fournies séparément ---
    medias_dispo = None
    medias_manquants = set()
    if args.medias:
        medias_dispo = set()
        for root, _, files in os.walk(args.medias):
            for f in files:
                medias_dispo.add(f)
        print(f"  {len(medias_dispo)} fichiers joints trouvés dans {args.medias}",
              file=sys.stderr)

    # --- notules ---
    out_notules = os.path.join(args.out, "notules")
    os.makedirs(out_notules, exist_ok=True)
    redirects = {}
    written = skipped = 0

    for row in tables.get(f"{p}_post", []):
        if not args.brouillons and not to_int(row.get("post_pub")):
            skipped += 1
            continue

        pid = to_int(row["post_id"])
        dt = to_datetime(row.get("post_dt")) or to_datetime(row.get("post_creadt"))
        if dt is None:
            skipped += 1
            continue

        titre = fix_encoding(row.get("post_titre") or "Sans titre").strip()
        # Le slug est repris TEL QUEL depuis Dotclear, y compris ses bizarreries
        # (tiret initial, tirets doublés). C'est ce que Google a indexé pendant
        # vingt ans : le « corriger » casserait la correspondance 1 pour 1 entre
        # ancienne et nouvelle adresse. On ne le fabrique que s'il est absent.
        slug = str(row.get("post_titre_url") or "").strip() or slugify(titre)
        chapo = rewrite_internal_links(fix_encoding(row.get("post_chapo") or ""), cat_urls)
        corps = rewrite_internal_links(fix_encoding(row.get("post_content") or ""), cat_urls)
        notes = rewrite_internal_links(fix_encoding(row.get("post_notes") or ""), cat_urls)
        chapo = rewrite_media_links(chapo, medias_dispo, medias_manquants, args.base_audio, args.garder_lourds_distants)
        corps = rewrite_media_links(corps, medias_dispo, medias_manquants, args.base_audio, args.garder_lourds_distants)
        notes = rewrite_media_links(notes, medias_dispo, medias_manquants, args.base_audio, args.garder_lourds_distants)

        cat_ids = post_cats.get(pid) or ([to_int(row["cat_id"])] if row.get("cat_id") else [])
        cat_objs = [categories[c] for c in dict.fromkeys(cat_ids) if c in categories]

        # Permalien conservé à l'identique de Dotclear : /css/AAAA/MM/JJ/ID-slug/
        url = "/css/%04d/%02d/%02d/%d-%s/" % (dt.year, dt.month, dt.day, pid, slug)
        redirects["%04d/%02d/%02d/%d-%s" % (dt.year, dt.month, dt.day, pid, slug)] = url

        # Garde-fou : si une colonne numérique contient du texte, c'est que le
        # découpage a dérapé sur cette ligne. On refuse d'écrire du JSON
        # corrompu et on le signale plutôt que de laisser passer en silence.
        suspect = False
        for champ in ("post_pub", "post_selected", "nb_comment", "nb_view"):
            valeur = row.get(champ)
            if valeur is None or valeur == "":
                continue
            try:
                int(str(valeur).strip())
            except ValueError:
                suspect = True
                ANOMALIES.append(
                    f"notule {pid} : le champ {champ} contient du texte "
                    f"({str(valeur)[:50]!r}) — ligne non importée"
                )
                break
        if suspect:
            skipped += 1
            continue

        notule = {
            "postId": to_int(pid),
            "titre": titre,
            "slug": slug,
            "url": url,
            "date": dt.isoformat(),
            "modifie": (to_datetime(row.get("post_upddt")).isoformat()
                        if to_datetime(row.get("post_upddt")) else None),
            "auteur": row.get("user_id") or "DavidLeMarrec",
            "langue": row.get("post_lang") or "fr",
            "categories": [{"nom": c["nom"], "slug": c["slug"]} for c in cat_objs],
            "chapoHtml": chapo,
            "corpsHtml": corps,
            "notesHtml": notes,
            "extrait": make_excerpt(chapo, corps),
            "nbCommentaires": to_int(row.get("nb_comment")),
            "commentaires": comments.get(pid, []),
            "epingle": bool(to_int(row.get("post_selected"))),
        }

        with open(os.path.join(out_notules, f"{pid}.json"), "w", encoding="utf-8") as fh:
            json.dump(notule, fh, ensure_ascii=False, indent=1)
        written += 1

    # --- fichiers annexes ---
    with open(os.path.join(args.out, "categories.json"), "w", encoding="utf-8") as fh:
        json.dump(sorted(categories.values(), key=lambda c: (c["ordre"], c["nom"])),
                  fh, ensure_ascii=False, indent=1)

    os.makedirs(args.public, exist_ok=True)
    with open(os.path.join(args.public, "redirects.json"), "w", encoding="utf-8") as fh:
        json.dump(redirects, fh, ensure_ascii=False)

    print(f"\n{written} notules écrites, {skipped} ignorées "
          f"(brouillons ou date manquante).", file=sys.stderr)
    print(f"Table de redirection : {len(redirects)} entrées.", file=sys.stderr)

    if ANOMALIES:
        chemin = os.path.join(args.out, "..", "anomalies.txt")
        with open(chemin, "w", encoding="utf-8") as fh:
            fh.write("\n".join(ANOMALIES))
        print(f"\n!! {len(ANOMALIES)} anomalies de découpage détectées — "
              f"détail dans {chemin}", file=sys.stderr)
    else:
        print("\nAucune anomalie de découpage détectée.", file=sys.stderr)

    if medias_dispo is not None:
        if medias_manquants:
            manquants_path = os.path.join(args.out, "..", "medias-manquants.txt")
            with open(manquants_path, "w", encoding="utf-8") as fh:
                fh.write("\n".join(sorted(medias_manquants)))
            # Ventilation par extension : indique s'il s'agit d'un dossier oublié
            # (une extension très majoritaire) ou de pertes éparses.
            par_ext = {}
            for nom in medias_manquants:
                ext = nom.rsplit(".", 1)[-1].lower() if "." in nom else "(sans)"
                par_ext[ext] = par_ext.get(ext, 0) + 1
            detail = ", ".join(f"{n} {e}" for e, n in
                               sorted(par_ext.items(), key=lambda x: -x[1]))
            print(f"\n{len(medias_manquants)} fichiers joints référencés mais "
                  f"absents ({detail}) — liste dans {manquants_path}", file=sys.stderr)
        else:
            print("\nTous les fichiers joints référencés ont été trouvés.",
                  file=sys.stderr)


if __name__ == "__main__":
    main()
