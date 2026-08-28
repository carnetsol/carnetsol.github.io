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
