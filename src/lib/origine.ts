/**
 * PROVENANCE D'UNE NOTULE, d'après son identifiant.
 *
 * Le site réunit sept sources. Chacune a reçu, à l'import, sa propre plage
 * de milliers d'identifiants — c'est la convention posée par les scripts
 * d'import, et elle est la seule marque fiable de l'origine : le bandeau
 * `.recuperation` vit dans le corps HTML, que le fil n'affiche pas.
 *
 * En deçà de 90 000 se trouve le fonds d'origine, celui de Dotclear.
 */

export interface Origine {
  /** Libellé affiché dans l'encart. */
  label: string;
  /** Classe CSS : `provenance` pour tout, plus une variante éventuelle. */
  variante: string;
}

const PLAGES: Record<number, Origine> = {
  92:  { label: '1 jour, 1 opéra',            variante: '' },
  93:  { label: 'Carnets sur sol (disques)',  variante: '' },
  94:  { label: 'Carnets sur sol (boueux)',   variante: '' },
  95:  { label: 'Carnets sur sol (notules)',  variante: '' },
  96:  { label: 'Carnets sur sol (concerts)', variante: '' },
  97:  { label: 'Belle Hémiole',              variante: '' },
  150: { label: 'Vidéo',                      variante: 'provenance-video' },
};

export function origine(postId: number): Origine {
  if (postId < 90000) return { label: 'Notule', variante: 'provenance-notule' };
  return PLAGES[Math.floor(postId / 1000)]
      ?? { label: 'Reprise', variante: '' };
}
