<?php
/**
 * Redirection permanente de l'ancien Carnets sur sol vers le nouveau.
 *
 *   ancien : http://operacritiques.free.fr/css/index.php?2006/07/04/273-slug
 *   nouveau: https://carnetsol.fr/css/2006/07/04/273-slug/
 *
 * À déposer dans operacritiques.free.fr/css/ en remplacement de l'index.php
 * de Dotclear. Renvoie un code HTTP 301 « déplacé définitivement », seul
 * mécanisme reconnu par les moteurs pour transférer l'antériorité et les
 * liens entrants d'une adresse à une autre.
 *
 * Aucune dépendance : ni base de données, ni fichier annexe. La structure des
 * adresses étant identique de part et d'autre, la transposition est calculée
 * plutôt que lue dans une table de 3000 lignes.
 */

$destination = 'https://carnetsol.fr';

// Dotclear plaçait l'information utile dans la chaîne de requête brute,
// sans nom de paramètre : index.php?2006/07/04/273-slug
$requete = isset($_SERVER['QUERY_STRING']) ? $_SERVER['QUERY_STRING'] : '';
$requete = urldecode($requete);

$cible = null;

if ($requete === '') {
    // Racine du blog
    $cible = '/css/';

} elseif (preg_match('#^(\d{4})/(\d{2})/(\d{2})/(\d+)(-[^&]*)?#', $requete, $m)) {
    // Permalien d'une notule. Le slug est FACULTATIF : Dotclear résolvait par
    // l'identifiant seul, et beaucoup de liens anciens sont tronqués
    // (« ?2013/04/04/2230 » ou « ?2013/04/04/2230-michelangelo »).
    $slug = isset($m[5]) ? $m[5] : '';
    $cible = sprintf('/css/%s/%s/%s/%s%s/', $m[1], $m[2], $m[3], $m[4], $slug);

} elseif (preg_match('#^(\d{4})/(\d{2})/(\d{2})/?$#', $requete, $m)) {
    // Archive d'un jour : on renvoie vers les archives générales.
    $cible = '/archives/';

} elseif (preg_match('#^(\d{4})/(\d{2})/?$#', $requete, $m)) {
    // Archive d'un mois
    $cible = '/archives/';

} elseif (preg_match('#^q=(.*)$#', $requete, $m)) {
    // Recherche
    $cible = '/css/recherche/?q=' . rawurlencode($m[1]);

} elseif (preg_match('#^feed(/.*)?$#', $requete)) {
    // Flux de syndication
    $cible = '/css/rss.xml';

} elseif (preg_match('#^([A-Za-z][\w\-]*)$#', $requete, $m)) {
    // Catégorie : index.php?Autour-de-pelleas-et-melisande
    $cible = '/categorie/' . $m[1] . '/';

} else {
    // Forme non reconnue : on renvoie vers l'accueil du blog plutôt que
    // de laisser une erreur. Mieux vaut une page utile qu'une impasse.
    $cible = '/css/';
}

header('HTTP/1.1 301 Moved Permanently');
header('Location: ' . $destination . $cible);
header('Cache-Control: max-age=2592000');   // 30 jours
exit;
