import { getCollection, type CollectionEntry } from 'astro:content';

/**
 * Le site mélange deux sources :
 *   - « notules »  : les archives Dotclear (JSON, corps en HTML)
 *   - « nouvelles » : ce que vous écrivez aujourd'hui (Markdown)
 * Ce module les réunit derrière une forme commune pour que les pages de
 * liste (fil, archives, catégories, RSS) n'aient pas à connaître la différence.
 */

export interface NotuleUnifiee {
  titre: string;
  url: string;
  date: Date;
  auteur: string;
  categories: { nom: string; slug: string }[];
  chapoHtml: string;
  extrait: string;
  nbCommentaires: number;
  /** 'archive' = corps HTML prêt ; 'markdown' = à rendre via render() */
  source: 'archive' | 'markdown';
  entree: CollectionEntry<'notules'> | CollectionEntry<'nouvelles'>;
}

/** Transforme un titre en fragment d'URL sans accent ni ponctuation. */
export function slugifier(valeur: string): string {
  return valeur
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
	.replace(/\|/g, '-')           // Remplace la barre verticale par un tiret
    .replace(/[^\w\s-]/g, '')
    .trim()
    .replace(/[-\s]+/g, '-')
    .replace(/^-+|-+$/g, '') || 'notule';
}

function texteBrut(html: string): string {
  return html.replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim();
}

/**
 * Résout les noms de catégories saisis en Markdown vers leur slug officiel,
 * pour que les nouvelles notules atterrissent dans les mêmes rubriques que
 * les archives plutôt que d'en créer des doublons.
 */
async function resolveurCategories() {
  const cats = await getCollection('categories');
  const parNom = new Map(cats.map((c) => [c.data.nom.toLowerCase(), c.data.slug]));
  return (nom: string) => ({
    nom,
    slug: parNom.get(nom.toLowerCase()) ?? slugifier(nom),
  });
}

/**
 * Charge les correctifs, indexés par identifiant de notule.
 * Séparés des archives pour survivre aux régénérations du dump.
 */
export async function chargerCorrections() {
  const liste = await getCollection('corrections');
  return new Map(liste.map((c) => [c.data.postId, c.data]));
}

/** Échappe une chaîne destinée à être utilisée dans une expression régulière. */
function echapper(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

/**
 * Applique un correctif aux données d'une notule d'archive.
 * Renvoie un nouvel objet ; l'original n'est pas modifié.
 */
export function appliquerCorrection(data: any, corr: any) {
  if (!corr) return data;
  const out = { ...data };

  for (const champ of ['titre', 'chapoHtml', 'corpsHtml', 'notesHtml',
                       'extrait', 'categories', 'date'] as const) {
    if (corr[champ] !== undefined) out[champ] = corr[champ];
  }

  // Les remplacements portent sur le corps déjà éventuellement remplacé.
  for (const r of corr.remplacements ?? []) {
    const motif = r.regex
      ? new RegExp(r.chercher, 'g')
      : new RegExp(echapper(r.chercher), 'g');
    out.corpsHtml = (out.corpsHtml ?? '').replace(motif, r.remplacer);
    out.chapoHtml = (out.chapoHtml ?? '').replace(motif, r.remplacer);
  }

  out.corrigee = true;
  return out;
}

/** Toutes les notules publiées, de la plus récente à la plus ancienne. */
export async function toutesLesNotules(): Promise<NotuleUnifiee[]> {
  const resoudre = await resolveurCategories();

  const correctifs = await chargerCorrections();

  const archives = (await getCollection('notules')).map((e) => {
    const d = appliquerCorrection(e.data, correctifs.get(e.data.postId));
    return {
      titre: d.titre,
      url: d.url,
      date: d.date,
      auteur: d.auteur,
      categories: d.categories,
      chapoHtml: d.chapoHtml,
      extrait: d.extrait,
      nbCommentaires: d.nbCommentaires,
      source: 'archive' as const,
      entree: e,
    };
  });

  const recentes = (await getCollection('nouvelles', ({ data }) => !data.brouillon))
    .map((e) => {
      const d = e.data.date;
      const an = d.getFullYear();
      const mois = String(d.getMonth() + 1).padStart(2, '0');
      const jour = String(d.getDate()).padStart(2, '0');
      const slug = slugifier(e.data.titre);
      return {
        titre: e.data.titre,
        // Même forme d'adresse que les archives, sans identifiant numérique.
        url: `/css/${an}/${mois}/${jour}/${slug}/`,
        date: d,
        auteur: e.data.auteur,
        categories: e.data.categories.map(resoudre),
        chapoHtml: e.data.chapo ? `<p>${e.data.chapo}</p>` : '',
        extrait: e.data.chapo || texteBrut(e.body ?? '').slice(0, 300),
        nbCommentaires: 0,
        source: 'markdown' as const,
        entree: e,
      };
    });

  return [...archives, ...recentes].sort(
    (a, b) => b.date.valueOf() - a.date.valueOf()
  );
}
