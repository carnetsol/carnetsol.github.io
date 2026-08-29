import { defineCollection, z } from 'astro:content';
import { glob, file } from 'astro/loaders';

/**
 * NORMALISATION UNICODE — forme composée (NFC).
 *
 * Une même chaîne s'écrit de deux façons en Unicode. « ὲ » peut être un
 * seul caractère (U+1F72), ou deux : un epsilon suivi d'un accent grave
 * combinant (U+03B5 U+0300). Les deux sont valides et devraient s'afficher
 * pareil — mais beaucoup de polices placent mal l'accent combinant, qui
 * apparaît alors décalé à côté de la lettre. D'où « Μηδὲ`ν » au lieu de
 * « Μηδὲν » : ce n'est pas une coquille, c'est un défaut de rendu.
 *
 * Le grec ancien polytonique est le cas le plus visible, parce qu'il
 * empile jusqu'à trois signes sur une voyelle, mais le français accentué
 * est concerné de la même façon.
 *
 * On normalise donc à la lecture, une fois pour toutes et pour toutes les
 * pages, plutôt que d'écrire un correctif par notule. L'opération est sans
 * risque sur du HTML — elle ne touche ni les balises ni les entités — et
 * elle est idempotente : la relancer ne change rien.
 */
const nfc = (s: string) => s.normalize('NFC');
const texteNfc = () => z.string().transform(nfc);

const categorieRef = z.object({
  nom: z.string(),
  slug: z.string(),
});

const commentaire = z.object({
  id: z.coerce.number().catch(0),
  auteur: z.string(),
  site: z.string().optional().default(''),
  date: z.string().nullable(),
  contenu: z.string().transform((s) => s.normalize('NFC')),
});

/**
 * ARCHIVES — une notule = un fichier JSON produit par la migration Dotclear.
 * Le corps reste du HTML brut : le convertir en Markdown casserait les
 * lecteurs audio, les tableaux et vingt ans de mises en forme.
 * On n'écrit pas dans cette collection à la main.
 */
const notules = defineCollection({
  loader: glob({
    pattern: '**/*.json',
    base: './src/content/notules',
    // IMPÉRATIF : sans cela, Astro prend le champ « slug » du JSON comme
    // identifiant d'entrée. Deux notules au slug identique s'écraseraient
    // l'une l'autre, et disparaîtraient du site sans le moindre message.
    // Le nom du fichier, lui, est unique par construction.
    generateId: ({ entry }) => entry.replace(/\.json$/, ''),
  }),
  schema: z.object({
    postId: z.coerce.number(),
    titre: texteNfc(),
    slug: texteNfc(),
    url: z.string(),
    date: z.coerce.date(),
    modifie: z.coerce.date().nullable().optional(),
    auteur: z.string().default('DavidLeMarrec'),
    langue: z.string().default('fr'),
    categories: z.array(categorieRef).default([]),
    chapoHtml: z.string().default('').transform(nfc),
    corpsHtml: z.string().default('').transform(nfc),
    notesHtml: z.string().default('').transform(nfc),
    extrait: z.string().default('').transform(nfc),
    // Image d'illustration explicite, posée par un import (la vignette
    // d'une vidéo YouTube, par exemple). Quand elle est vide, le fil
    // cherche la première image du corps.
    vignette: z.string().default(''),
    nbCommentaires: z.coerce.number().catch(0).default(0),
    commentaires: z.array(commentaire).default([]),
    epingle: z.coerce.boolean().catch(false).default(false),
  }),
});

/**
 * NOUVELLES NOTULES — Markdown, écrites à la main.
 * Un fichier .md dans src/content/nouvelles/ suffit : l'en-tête donne le
 * titre, la date et les catégories, le reste du fichier est le texte.
 */
const nouvelles = defineCollection({
  loader: glob({ pattern: '**/*.{md,mdx}', base: './src/content/nouvelles' }),
  schema: z.object({
    titre: texteNfc(),
    date: z.coerce.date(),
    // Noms de catégories tels qu'ils apparaissent sur le site,
    // ex. ["Disques et représentations", "L'horrible Richard Wagner"]
    categories: z.array(z.string()).default([]),
    chapo: z.string().default('').transform(nfc),
    auteur: z.string().default('DavidLeMarrec'),
    // Passer à true pour garder la notule hors du site.
    brouillon: z.boolean().default(false),
  }),
});

/**
 * CORRECTIFS — retouches apportées aux notules d'archive.
 *
 * Les fichiers {postId}.json de src/content/notules/ sont RÉGÉNÉRÉS à chaque
 * migration : les modifier à la main serait perdu à la prochaine exécution.
 * On dépose donc ici un fichier par notule corrigée, nommé <postId>.json,
 * appliqué au moment de la compilation. Il survit à toutes les régénérations.
 *
 * Deux façons de corriger, combinables :
 *   - remplacer un champ entier   (titre, chapoHtml, corpsHtml, categories…)
 *   - « remplacements » : une liste chercher/remplacer appliquée au corps,
 *     pratique pour une coquille sans recopier 15 000 caractères.
 */
const corrections = defineCollection({
  loader: glob({ pattern: '**/*.json', base: './src/content/corrections' }),
  schema: z.object({
    postId: z.coerce.number(),
    note: z.string().optional(),
    // true = la notule disparaît du site (fil, archives, catégories, RSS,
    // page propre). Le fichier d'origine reste en place : c'est le moyen
    // de dépublier sans rien détruire, et sans que la prochaine migration
    // ne ressuscite la notule.
    depublier: z.boolean().default(false),
    titre: z.string().optional(),
    chapoHtml: z.string().optional(),
    corpsHtml: z.string().optional(),
    notesHtml: z.string().optional(),
    extrait: z.string().optional(),
    categories: z.array(categorieRef).optional(),
    date: z.coerce.date().optional(),
    remplacements: z.array(z.object({
      chercher: z.string(),
      remplacer: z.string(),
      // true = expression régulière, false (défaut) = texte littéral
      regex: z.boolean().default(false),
    })).default([]),
  }),
});

const categories = defineCollection({
  loader: file('./src/content/categories.json'),
  schema: z.object({
    id: z.coerce.number(),
    nom: z.string(),
    description: z.string().default(''),
    slug: texteNfc(),
    ordre: z.coerce.number().catch(999).default(999),
  }),
});

export const collections = { notules, nouvelles, corrections, categories };
