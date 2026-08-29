/**
 * Remise au net des textes bruts issus de la migration.
 *
 * LE PROBLÈME
 * -----------
 * Le champ « extrait » est du texte, pas du HTML : il s'affiche tel quel,
 * et le moteur de rendu échappe ce qu'il contient. Or certains extraits
 * portent encore des entités HTML visibles :
 *
 *     N&#x27;entend-on pas le glas…
 *
 * L'origine est un double échappement dans le corpus Dotclear : le texte y
 * était écrit « N&amp;#x27;entend-on ». La migration désamorce une couche —
 * il reste « &#x27; » — et l'affichage, qui traite la chaîne comme du texte,
 * montre l'entité au lieu de l'apostrophe.
 *
 * LA CORRECTION
 * -------------
 * On désamorce jusqu'à stabilité, avec une borne. Une boucle non bornée
 * serait dangereuse : « &amp;amp;amp;… » la ferait tourner longtemps, et
 * surtout un texte qui parle LÉGITIMEMENT d'entités HTML finirait déformé.
 * Trois passes suffisent à tout ce que contient ce corpus.
 *
 * C'est un correctif d'affichage, pas de données : les fichiers JSON sont
 * régénérés à chaque migration, il serait vain d'y toucher.
 */

const ENTITES: Record<string, string> = {
  '&amp;': '&', '&lt;': '<', '&gt;': '>', '&quot;': '"',
  '&apos;': "'", '&nbsp;': ' ', '&hellip;': '…', '&laquo;': '«',
  '&raquo;': '»', '&rsquo;': '\u2019', '&lsquo;': '\u2018',
  '&mdash;': '—', '&ndash;': '–', '&oelig;': 'œ', '&OElig;': 'Œ',
  '&eacute;': 'é', '&egrave;': 'è', '&ecirc;': 'ê', '&agrave;': 'à',
  '&ccedil;': 'ç', '&ugrave;': 'ù', '&ocirc;': 'ô', '&icirc;': 'î',
  '&acirc;': 'â', '&ucirc;': 'û', '&euml;': 'ë', '&iuml;': 'ï',
};

function unEchappement(texte: string): string {
  return texte
    // &#39; et &#x27; : numérique décimal et hexadécimal
    .replace(/&#(\d+);/g, (_, n) => String.fromCodePoint(Number(n)))
    .replace(/&#[xX]([0-9a-fA-F]+);/g, (_, n) =>
      String.fromCodePoint(parseInt(n, 16)))
    .replace(/&[a-zA-Z]+;/g, (e) => ENTITES[e] ?? e);
}

/** Texte prêt à être affiché : entités résolues, balises et blancs nettoyés. */
export function texteLisible(brut: string | undefined | null): string {
  if (!brut) return '';
  let texte = brut;

  for (let passe = 0; passe < 3; passe++) {
    const suivant = unEchappement(texte);
    if (suivant === texte) break;
    texte = suivant;
  }

  // Une balise ayant pu réapparaître au désamorçage, on renettoie.
  texte = texte.replace(/<[^>]+>/g, ' ');

  return texte.replace(/\s+/g, ' ').trim();
}
