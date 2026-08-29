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

/**
 * Identifiants des notules dépubliées, d'après les correctifs.
 * Un seul endroit pour la vérité : toutes les pages passent par là.
 */
export async function chargerDepubliees(): Promise<Set<number>> {
  const liste = await getCollection('corrections');
  return new Set(
    liste.filter((c) => c.data.depublier).map((c) => c.data.postId)
  );
}

/**
 * Retire d'une liste de notules celles qui sont dépubliées.
 * À appeler dans TOUTE page qui liste ou génère des notules : fil,
 * archives, catégories, RSS, permaliens. Une notule oubliée quelque part
 * resterait accessible, ce qui viderait la dépublication de son sens.
 */
export async function notulesPubliees<T extends { data: { postId: number } }>(
  notules: T[]
): Promise<T[]> {
  const masquees = await chargerDepubliees();
  return notules.filter((n) => !masquees.has(n.data.postId));
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

/**
 * Adresse d'une notule écrite en Markdown.
 *
 * Avec un postId, on reproduit exactement la forme de Dotclear, pour que
 * les liens de l'ancien site continuent de tomber juste. Sans lui,
 * l'adresse se passe de numéro.
 */
export function urlDeNouvelle(
  data: { titre: string; date: Date; postId?: number; slug?: string }
) {
  const d = data.date;
  const an = d.getFullYear();
  const mois = String(d.getMonth() + 1).padStart(2, '0');
  const jour = String(d.getDate()).padStart(2, '0');
  const slug = data.slug || slugifier(data.titre);
  const segment = data.postId ? `${data.postId}-${slug}` : slug;
  return `/css/${an}/${mois}/${jour}/${segment}/`;
}

/**
 * TOUTES les notules à lister, archives ET markdown confondues.
 *
 * C'est la fonction que doivent appeler le fil, les archives, les
 * chapitres, le flux RSS et l'encart Antiquités. Auparavant chacun lisait
 * la seule collection « notules » : une notule écrite en Markdown avait sa
 * page, mais n'apparaissait dans AUCUNE liste. Elle n'existait, en
 * pratique, que pour qui en connaissait déjà l'adresse.
 *
 * Les entrées Markdown reçoivent ici la même forme que les archives —
 * même champ `data`, mêmes noms — pour que NotuleCard et les pages de
 * liste n'aient pas à distinguer les deux origines.
 *
 * Une réserve à connaître : `corpsHtml` reste vide pour le Markdown, dont
 * le rendu ne se fait qu'à l'ouverture de la page. Le fil ne peut donc pas
 * y pêcher une illustration ; renseignez `vignette` dans l'en-tête si vous
 * en voulez une.
 */
export async function notulesPourListe() {
  const masquees = await chargerDepubliees();
  const correctifs = await chargerCorrections();
  const resoudre = await resolveurCategories();

  const archives = (await getCollection('notules'))
    .filter((e) => !masquees.has(e.data.postId))
    .map((e) => ({
      id: e.id,
      data: appliquerCorrection(e.data, correctifs.get(e.data.postId)),
    }));

  const recentes = (await getCollection('nouvelles', ({ data }) => !data.brouillon))
    .map((e) => ({
      id: e.id,
      data: {
        postId: e.data.postId ?? 0,
        titre: e.data.titre,
        slug: e.data.slug || slugifier(e.data.titre),
        url: urlDeNouvelle(e.data),
        date: e.data.date,
        auteur: e.data.auteur,
        langue: 'fr',
        categories: e.data.categories.map(resoudre),
        chapoHtml: e.data.chapo ? `<p>${e.data.chapo}</p>` : '',
        corpsHtml: '',
        notesHtml: '',
        extrait: e.data.chapo || texteBrut(e.body ?? '').slice(0, 300),
        vignette: e.data.vignette ?? '',
        nbCommentaires: 0,
        commentaires: [],
        epingle: false,
      },
    }));

  return [...archives, ...recentes].sort(
    (a, b) => b.data.date.valueOf() - a.data.date.valueOf()
  );
}

/** Toutes les notules publiées, de la plus récente à la plus ancienne. */
export async function toutesLesNotules(): Promise<NotuleUnifiee[]> {
  const resoudre = await resolveurCategories();

  const correctifs = await chargerCorrections();

  const masquees = await chargerDepubliees();

  const archives = (await getCollection('notules'))
    .filter((e) => !masquees.has(e.data.postId))
    .map((e) => {
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
