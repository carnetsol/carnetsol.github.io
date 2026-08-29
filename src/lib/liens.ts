/**
 * Ouverture des liens SORTANTS dans un nouvel onglet.
 *
 * Le corps des notules est du HTML hérité de Dotclear : on ne peut pas le
 * modifier à la source (les JSON sont régénérés à chaque migration), donc
 * la réécriture se fait au moment de la compilation, sur la chaîne HTML.
 *
 * Sont considérés comme INTERNES, et gardés dans le même onglet :
 *   - les adresses relatives (/css/…, #ancre, ../…)
 *   - carnetsol.fr et ses sous-domaines, l'aperçu Netlify
 *   - mailto:, tel:, javascript:
 * Tout le reste part dans un nouvel onglet.
 *
 * rel="noopener" est indispensable : sans lui, la page ouverte peut
 * manipuler la page d'origine via window.opener. "noreferrer" s'y ajoute
 * pour ne pas transmettre l'adresse de provenance.
 */

const INTERNES = [
  'carnetsol.fr',
  'www.carnetsol.fr',
  'carnetsol.netlify.app',
  'carnetsol.github.io',
];

/** Une adresse est-elle sortante ? */
export function estSortant(href: string): boolean {
  const h = href.trim();
  if (!h) return false;
  // Ancres, chemins relatifs, protocoles non navigables.
  if (/^(#|\/|\.|\?)/.test(h)) return false;
  if (/^(mailto|tel|javascript|data):/i.test(h)) return false;

  const m = h.match(/^https?:\/\/([^/:?#]+)/i);
  if (!m) return false;                 // ni relatif ni http : on ne touche pas
  return !INTERNES.includes(m[1].toLowerCase());
}

/**
 * Ajoute target et rel aux balises <a> sortantes d'une chaîne HTML.
 * Les balises qui portent déjà un target sont laissées telles quelles :
 * l'intention de l'auteur prime.
 */
export function ouvrirDehors(html: string): string {
  if (!html) return html;

  return html.replace(/<a\b([^>]*)>/gi, (balise, attributs) => {
    if (/\btarget\s*=/i.test(attributs)) return balise;

    const href = attributs.match(/\bhref\s*=\s*("([^"]*)"|'([^']*)'|([^\s>]+))/i);
    if (!href) return balise;
    const valeur = href[2] ?? href[3] ?? href[4] ?? '';
    if (!estSortant(valeur)) return balise;

    // Complète un rel existant plutôt que de le remplacer : beaucoup de
    // liens de commentaires portent déjà rel="nofollow".
    const relExistant = attributs.match(/\brel\s*=\s*("([^"]*)"|'([^']*)'|([^\s>]+))/i);
    if (relExistant) {
      const valeurs = new Set(
        (relExistant[2] ?? relExistant[3] ?? relExistant[4] ?? '').split(/\s+/).filter(Boolean)
      );
      valeurs.add('noopener');
      valeurs.add('noreferrer');
      const remplace = attributs.replace(
        relExistant[0], `rel="${[...valeurs].join(' ')}"`
      );
      return `<a${remplace} target="_blank">`;
    }

    return `<a${attributs} target="_blank" rel="noopener noreferrer">`;
  });
}

/**
 * Renvoi vers l'ancienne version d'une notule, quand elle contient un mp3.
 *
 * Les lecteurs audio hérités de Dotclear ne fonctionnent pas tous sur le
 * nouveau site. En attendant, on place à côté du lecteur un renvoi vers la
 * notule d'origine, restée en ligne sur operacritiques.free.fr.
 *
 * L'avertissement n'est posé qu'UNE fois : après le premier lecteur s'il y
 * en a un balisé <audio>, sinon en fin de corps. Répéter la phrase à chaque
 * occurrence de « .mp3 » encombrerait les notules qui en citent dix.
 */
export function avertirMp3(html: string, urlAncienne: string | null): string {
  if (!html || !urlAncienne) return html;
  if (!/\.mp3\b/i.test(html) && !/<audio\b/i.test(html)) return html;

  const note =
    '\n<p class="note-mp3">Si le mp3 n\'est pas encore fonctionnel, voyez '
    + `<a href="${urlAncienne}" target="_blank" rel="noopener noreferrer">`
    + 'cette ancienne version de la notule</a>.</p>\n';

  const fin = html.search(/<\/audio\s*>/i);
  if (fin !== -1) {
    const apres = html.indexOf('>', fin) + 1;
    return html.slice(0, apres) + note + html.slice(apres);
  }
  return html + note;
}
