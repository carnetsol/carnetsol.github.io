#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Récupération des notules perdues lors du crash, depuis une capture HTTrack
de Wayback Machine.

Fonctionne en deux temps :
    1. par défaut, RAPPORT SEUL : indique ce qui serait ajouté, sans rien écrire
    2. avec --ecrire, crée réellement les fichiers JSON manquants

Usage :
    python recuperer_httrack.py "chemin\\capture" src\\content\\notules
    python recuperer_httrack.py "chemin\\capture" src\\content\\notules --ecrire

Points traités :
  - suppression des préfixes Wayback (…/web/20250321105700/, im_, if_, js_)
  - réécriture des liens internes vers les nouvelles adresses /css/…
  - réécriture des médias vers /medias/…
  - récupération des commentaires quand la page individuelle a été capturée
  - dédoublonnage par identifiant Dotclear, puis par date + titre
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
from html.parser import HTMLParser

MARQUEUR = ("<p class=\"recuperation\"><em>[récupération du crash de 2025]</em></p>\n")

MOIS_FR = {
    "janvier": 1, "février": 2, "fevrier": 2, "mars": 3, "avril": 4, "mai": 5,
    "juin": 6, "juillet": 7, "août": 8, "aout": 8, "septembre": 9,
    "octobre": 10, "novembre": 11, "décembre": 12, "decembre": 12,
}

# ---------------------------------------------------------------------------
# Nettoyage des adresses Wayback
# ---------------------------------------------------------------------------

# https://web.archive.org/web/20250321105700im_/http://exemple.fr/x  ->  http://exemple.fr/x
WAYBACK = re.compile(
    r"https?://web\.archive\.org/web/\d{8,14}(?:[a-z]{2}_)?/", re.IGNORECASE
)

# HTTrack réécrit aussi certaines adresses Wayback en chemins RELATIFS,
# en remplaçant « https:// » par « https_/ » :
#   ../../../../20250301153405im_/https_/exemple.fr/image.jpg
# Sans cette règle, ces liens-là restent brisés.
WAYBACK_RELATIF = re.compile(
    r"(?:\.\./)*\d{8,14}(?:[a-z]{2}_)?/(https?)_/", re.IGNORECASE
)

# Lien interne vers une notule de l'ancien site
LIEN_NOTULE = re.compile(
    r"https?://operacritiques\.free\.fr/(?:css|dotclear)/index\.php\?"
    r"(\d{4})/(\d{2})/(\d{2})/(\d+)-([^\"'\s&#]*)",
    re.IGNORECASE,
)
LIEN_CATEGORIE = re.compile(
    r"https?://operacritiques\.free\.fr/(?:css|dotclear)/index\.php\?"
    r"([A-Za-z][\w\-]*)",
    re.IGNORECASE,
)
LIEN_MEDIA = re.compile(
    r"https?://operacritiques\.free\.fr/(?:css/)?(?:images|sons|documents)?/?"
    r"([^\"'>]+\.(?:jpe?g|png|gif|webp|svg|bmp|jfif|tiff?|mp3|mp4|pdf|ogg|m4a|flac|wav|avi|wmv|flv|mov|swf|mid|zip))(?=[\"'\s>])",
    re.IGNORECASE,
)

# Beaucoup de notules écrivent leurs médias en chemin relatif à la racine,
# sans nom de domaine :  <img src="/css/images/evgeny_kissin.jpg">
# Sans cette règle, ces liens pointent vers une adresse inexistante sur le
# nouveau site.
MEDIA_RACINE = re.compile(
    r"(?<=[\"'])/(?:css/)?(?:images|sons|documents)/"
    r"([^\"'>]+\.(?:jpe?g|png|gif|webp|svg|bmp|jfif|tiff?|mp3|mp4|pdf|ogg|m4a|flac|wav|avi|wmv|flv|mov|swf|mid|zip))(?=[\"'])",
    re.IGNORECASE,
)


# Formats laissés sur l'ancien hébergement : ce sont les fichiers lourds,
# que l'on ne rapatrie pas dans le dépôt (cf. --garder-lourds-distants
# du script de migration).
EXT_LOURDES = (".mp3", ".mp4", ".flac", ".wav", ".m4a", ".ogg",
               ".avi", ".wmv", ".flv", ".mov")


def nettoyer_liens(html_src, garder_lourds_distants=False):
    """Retire les préfixes Wayback puis rapatrie les liens internes."""
    s = WAYBACK.sub("", html_src)
    s = WAYBACK_RELATIF.sub(lambda m: m.group(1) + "://", s)
    s = LIEN_NOTULE.sub(
        lambda m: "/css/%s/%s/%s/%s-%s/" % m.groups(), s
    )

    def media(m):
        nom = os.path.basename(m.group(1))
        # Audio et vidéo restent servis par operacritiques.free.fr :
        # on rétablit l'adresse complète plutôt qu'un chemin local.
        if garder_lourds_distants and nom.lower().endswith(EXT_LOURDES):
            return "http://operacritiques.free.fr/css/images/" + nom
        return "/medias/" + nom

    s = LIEN_MEDIA.sub(media, s)
    s = MEDIA_RACINE.sub(media, s)
    s = LIEN_CATEGORIE.sub(lambda m: "/categorie/%s/" % m.group(1), s)
    # Bandeau et scripts Wayback résiduels
    s = re.sub(r"<script[^>]*archive\.org[^>]*>.*?</script>", "", s, flags=re.S | re.I)
    s = re.sub(r"<!--\s*(BEGIN|END) WAYBACK TOOLBAR INSERT\s*-->", "", s, flags=re.I)
    return s


# ---------------------------------------------------------------------------
# Découpage des blocs <div class="post">
# ---------------------------------------------------------------------------

class ExtracteurBlocs(HTMLParser):
    """Isole le contenu des balises portant une classe donnée, en suivant
    correctement l'imbrication (ce qu'une expression régulière ne sait pas faire)."""

    def __init__(self, balise, classe):
        super().__init__(convert_charrefs=False)
        self.balise, self.classe = balise, classe
        self.blocs = []
        self._profondeur = None
        self._tampon = []

    def handle_starttag(self, tag, attrs):
        d = dict(attrs)
        if self._profondeur is None:
            if tag == self.balise and self.classe in (d.get("class") or "").split():
                self._profondeur = 1
                self._tampon = []
                self._attrs_ouverture = d
                return
        else:
            if tag == self.balise:
                self._profondeur += 1
            self._tampon.append(self.get_starttag_text())

    def handle_endtag(self, tag):
        if self._profondeur is None:
            return
        if tag == self.balise:
            self._profondeur -= 1
            if self._profondeur == 0:
                self.blocs.append(("".join(self._tampon), self._attrs_ouverture))
                self._profondeur = None
                return
        self._tampon.append("</%s>" % tag)

    def handle_startendtag(self, tag, attrs):
        if self._profondeur is not None:
            self._tampon.append(self.get_starttag_text())

    def handle_data(self, data):
        if self._profondeur is not None:
            self._tampon.append(data)

    def handle_entityref(self, name):
        if self._profondeur is not None:
            self._tampon.append("&%s;" % name)

    def handle_charref(self, name):
        if self._profondeur is not None:
            self._tampon.append("&#%s;" % name)

    def handle_comment(self, data):
        if self._profondeur is not None:
            self._tampon.append("<!--%s-->" % data)


def blocs(html_src, balise, classe):
    p = ExtracteurBlocs(balise, classe)
    try:
        p.feed(html_src)
    except Exception:
        pass
    return p.blocs


def texte_seul(h):
    return html.unescape(re.sub(r"<[^>]+>", " ", h or "")).strip()


def normaliser_espaces(s):
    return re.sub(r"\s+", " ", s or "").strip()


# ---------------------------------------------------------------------------
# Lecture d'une notule
# ---------------------------------------------------------------------------

def parser_date_fr(texte):
    """« vendredi 28 février 2025 » -> datetime(2025, 2, 28)"""
    t = normaliser_espaces(texte).lower()
    m = re.search(r"(\d{1,2})\s+([a-zàâçéèêëîïôûùüÿñ]+)\s+(\d{4})", t)
    if not m:
        return None
    jour, mois, annee = int(m.group(1)), m.group(2), int(m.group(3))
    if mois not in MOIS_FR:
        return None
    try:
        return datetime(annee, MOIS_FR[mois], jour)
    except ValueError:
        return None


def slugifier(v):
    v = unicodedata.normalize("NFKD", v or "").encode("ascii", "ignore").decode()
    v = re.sub(r"[^\w\s-]", "", v).strip().lower()
    return re.sub(r"[-\s]+", "-", v).strip("-") or "notule"


def lire_notules(chemin, garder_lourds_distants=False):
    """Retourne la liste des notules trouvées dans un fichier HTML capturé."""
    brut = open(chemin, encoding="utf-8", errors="replace").read()
    src = nettoyer_liens(brut, garder_lourds_distants)
    trouvees = []

    for corps_bloc, _ in blocs(src, "div", "post"):
        # -- titre, identifiant, adresse d'origine
        mt = re.search(
            r'<h2[^>]*id="p(\d+)"[^>]*class="post-title"[^>]*>(.*?)</h2>',
            corps_bloc, re.S)
        if not mt:
            mt = re.search(
                r'<h2[^>]*class="post-title"[^>]*id="p(\d+)"[^>]*>(.*?)</h2>',
                corps_bloc, re.S)
        if not mt:
            continue
        post_id = int(mt.group(1))
        bloc_titre = mt.group(2)
        titre = normaliser_espaces(texte_seul(bloc_titre))

        # -- date : d'abord l'adresse (fiable), sinon le libellé français
        date = None
        slug = slugifier(titre)
        mu = re.search(r'href="/css/(\d{4})/(\d{2})/(\d{2})/(\d+)-([^"]*)/"', bloc_titre)
        if mu:
            date = datetime(int(mu.group(1)), int(mu.group(2)), int(mu.group(3)))
            slug = mu.group(5).rstrip("/")
        if date is None:
            md = re.search(r'class="day-date"[^>]*>(.*?)</p>', corps_bloc, re.S)
            if md:
                date = parser_date_fr(texte_seul(md.group(1)))
        if date is None:
            continue

        # -- corps
        contenus = blocs(corps_bloc, "div", "post-content")
        corps = contenus[0][0] if contenus else ""
        chapos = blocs(corps_bloc, "div", "post-chapo")
        chapo = chapos[0][0] if chapos else ""

        # -- catégories, lues dans le bandeau d'informations
        cats = []
        minfo = re.search(r'class="post-info"[^>]*>(.*?)</p>', corps_bloc, re.S)
        if minfo:
            for href, libelle in re.findall(
                    r'href="/categorie/([^"/]+)/"[^>]*>(.*?)</a>', minfo.group(1), re.S):
                nom = normaliser_espaces(texte_seul(libelle))
                if nom:
                    cats.append({"nom": nom, "slug": href})

        trouvees.append({
            "postId": post_id,
            "titre": titre,
            "slug": slug,
            "url": "/css/%04d/%02d/%02d/%d-%s/" % (date.year, date.month,
                                                   date.day, post_id, slug),
            "date": date,
            "chapoHtml": chapo.strip(),
            "corpsHtml": corps.strip(),
            "categories": cats,
            "commentaires": lire_commentaires(src, post_id),
            "source": os.path.basename(chemin),
        })

    return trouvees


def lire_commentaires(src, post_id):
    """Les commentaires ne figurent que sur les pages de notule individuelles."""
    out = []
    for bloc, _ in blocs(src, "div", "comment"):
        auteur, date_txt = "Anonyme", None
        mi = re.search(r'class="comment-info"[^>]*>(.*?)</p>', bloc, re.S)
        if mi:
            info = texte_seul(mi.group(1))
            ma = re.search(r"De\s+(.+?)\s+le\s+(.+)", info)
            if ma:
                auteur = normaliser_espaces(ma.group(1))
                date_txt = normaliser_espaces(ma.group(2))
            else:
                auteur = normaliser_espaces(info)[:80] or "Anonyme"
        contenus = blocs(bloc, "blockquote", "") or []
        texte = contenus[0][0] if contenus else re.sub(
            r'<p class="comment-info".*?</p>', "", bloc, flags=re.S)
        d = parser_date_fr(date_txt or "")
        out.append({
            "id": 0,
            "auteur": auteur,
            "site": "",
            "date": d.isoformat() if d else None,
            "contenu": texte.strip(),
        })
    return out


# ---------------------------------------------------------------------------
# Programme principal
# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("capture", help="dossier de la capture HTTrack")
    ap.add_argument("notules", help="dossier src/content/notules")
    ap.add_argument("--ecrire", action="store_true",
                    help="écrire réellement les fichiers (sinon, rapport seul)")
    ap.add_argument("--garder-lourds-distants", dest="garder_lourds_distants",
                    action="store_true",
                    help="mp3/mp4/flac/wav... restent liés vers "
                         "operacritiques.free.fr au lieu de /medias/ "
                         "(à utiliser si le script de migration a la même "
                         "option, pour rester cohérent)")
    ap.add_argument("--rapport", default="recuperation-rapport.txt")
    args = ap.parse_args()

    # --- ce qui existe déjà ---
    # ATTENTION : après le crash, Dotclear a REATTRIBUÉ les identifiants libérés
    # à de nouvelles notules. Un même postId peut donc désigner deux textes
    # différents. L'identifiant ne vaut donc RIEN comme critère d'identité :
    # seule la paire (date, titre) fait foi, et aucun fichier existant ne doit
    # être écrasé.
    existants_datetitre = {}
    existants_url = set()
    ids_occupes = {}
    for nom in os.listdir(args.notules):
        if not nom.endswith(".json"):
            continue
        with open(os.path.join(args.notules, nom), encoding="utf-8") as fh:
            d = json.load(fh)
        cle = (d["date"][:10], normaliser_espaces(d["titre"]).lower())
        existants_datetitre[cle] = d
        existants_url.add(d["url"])
        ids_occupes.setdefault(int(d["postId"]), []).append(
            (d["date"][:10], d["titre"])
        )
    print(f"{len(existants_datetitre)} notules déjà présentes sur le site",
          file=sys.stderr)

    # --- parcours de la capture ---
    if not os.path.isdir(args.capture):
        print(f"ERREUR : le dossier « {args.capture} » n'existe pas.",
              file=sys.stderr)
        print("Vérifiez le chemin (espaces, accents, nom exact du dossier).",
              file=sys.stderr)
        sys.exit(1)

    fichiers = []
    for racine, _, noms in os.walk(args.capture):
        for n in noms:
            if n.lower().endswith((".html", ".htm")):
                fichiers.append(os.path.join(racine, n))

    if not fichiers:
        print(f"ERREUR : aucun fichier .html sous « {args.capture} ».",
              file=sys.stderr)
        print("Le dossier existe mais ne contient pas la capture : visez le "
              "dossier qui contient web.archive.org/…", file=sys.stderr)
        sys.exit(1)

    print(f"{len(fichiers)} fichiers HTML à examiner…", file=sys.stderr)

    # Une notule peut apparaître dans plusieurs captures : on garde la version
    # la plus complète (corps le plus long, commentaires présents).
    meilleures = {}
    for i, f in enumerate(fichiers, 1):
        if i % 200 == 0:
            print(f"  {i}/{len(fichiers)}…", file=sys.stderr)
        try:
            for n in lire_notules(f, args.garder_lourds_distants):
                cle = n["postId"]
                ancien = meilleures.get(cle)
                score = len(n["corpsHtml"]) + 5000 * len(n["commentaires"])
                if ancien is None or score > ancien["_score"]:
                    n["_score"] = score
                    meilleures[cle] = n
        except Exception as e:
            print(f"  !! {os.path.basename(f)} : {e}", file=sys.stderr)

    # --- tri entre nouvelles et déjà présentes ---
    a_ajouter, deja, conflits = [], [], []
    for n in meilleures.values():
        cle_dt = (n["date"].strftime("%Y-%m-%d"),
                  normaliser_espaces(n["titre"]).lower())
        if cle_dt in existants_datetitre:
            deja.append(n)
            continue
        # L'identifiant est-il déjà utilisé par une AUTRE notule ?
        occupant = ids_occupes.get(n["postId"])
        if occupant:
            conflits.append((n, occupant))
        a_ajouter.append(n)

    a_ajouter.sort(key=lambda x: x["date"])

    lignes = [
        f"Notules trouvées dans la capture : {len(meilleures)}",
        f"  déjà présentes (date + titre)  : {len(deja)}",
        f"  À AJOUTER                      : {len(a_ajouter)}",
        f"  dont identifiant réattribué    : {len(conflits)}",
        "",
    ]
    if conflits:
        lignes.append("--- identifiants réutilisés par Dotclear après le crash ---")
        lignes.append("(la notule récupérée est conservée sous un autre nom de")
        lignes.append(" fichier et une autre adresse ; rien n'est écrasé)")
        for n, occupant in conflits:
            lignes.append("  id %d : récupérée « %s » (%s)"
                          % (n["postId"], n["titre"][:55],
                             n["date"].strftime("%Y-%m-%d")))
            for dt, t in occupant:
                lignes.append("          déjà pris par « %s » (%s)" % (t[:55], dt))
        lignes.append("")
    lignes.append("--- à ajouter ---")
    for n in a_ajouter:
        lignes.append(
            "  [%d] %s — %s (%d caractères, %d commentaires)"
            % (n["postId"], n["date"].strftime("%Y-%m-%d"), n["titre"][:70],
               len(n["corpsHtml"]), len(n["commentaires"]))
        )
    rapport = "\n".join(lignes)
    print("\n" + rapport)
    with open(args.rapport, "w", encoding="utf-8") as fh:
        fh.write(rapport)
    print(f"\nRapport écrit dans {args.rapport}", file=sys.stderr)

    if not args.ecrire:
        print("\n>>> RAPPORT SEUL — aucun fichier créé. "
              "Relancez avec --ecrire pour appliquer.", file=sys.stderr)
        return

    ecrits = 0
    for n in a_ajouter:
        # Nom de fichier distinct de la numérotation Dotclear : impossible
        # d'écraser une notule existante, même en cas d'identifiant réattribué.
        base = "recup-%s-%s" % (n["date"].strftime("%Y%m%d"), n["slug"][:60])
        chemin = os.path.join(args.notules, base + ".json")
        if os.path.exists(chemin):
            print(f"  !! {base}.json existe déjà — ignoré", file=sys.stderr)
            continue

        # Adresse : on garde celle d'origine si elle est libre, sinon on la
        # désambiguïse plutôt que de créer deux pages à la même adresse.
        url = n["url"]
        if url in existants_url:
            url = "/css/%04d/%02d/%02d/%s-recuperee/" % (
                n["date"].year, n["date"].month, n["date"].day, n["slug"][:60])
        existants_url.add(url)

        corps = MARQUEUR + n["corpsHtml"]
        extrait = normaliser_espaces(texte_seul(n["chapoHtml"] or n["corpsHtml"]))[:300]
        notule = {
            "postId": n["postId"],
            "titre": n["titre"],
            "slug": n["slug"],
            "url": url,
            "date": n["date"].isoformat(),
            "modifie": None,
            "auteur": "DavidLeMarrec",
            "langue": "fr",
            "categories": n["categories"],
            "chapoHtml": n["chapoHtml"],
            "corpsHtml": corps,
            "notesHtml": "",
            "extrait": extrait,
            "nbCommentaires": len(n["commentaires"]),
            "commentaires": n["commentaires"],
            "epingle": False,
            "recuperee": True,
        }
        with open(chemin, "w", encoding="utf-8") as fh:
            json.dump(notule, fh, ensure_ascii=False, indent=1)
        ecrits += 1

    print(f"\n{ecrits} notules récupérées et écrites.", file=sys.stderr)


if __name__ == "__main__":
    main()
