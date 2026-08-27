import { defineCollection, z } from 'astro:content';
import { glob, file } from 'astro/loaders';

const categorieRef = z.object({
  nom: z.string(),
  slug: z.string(),
});

const commentaire = z.object({
  id: z.coerce.number().catch(0),
  auteur: z.string(),
  site: z.string().optional().default(''),
  date: z.string().nullable(),
  contenu: z.string(),
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
    titre: z.string(),
    slug: z.string(),
    url: z.string(),
    date: z.coerce.date(),
    modifie: z.coerce.date().nullable().optional(),
    auteur: z.string().default('DavidLeMarrec'),
    langue: z.string().default('fr'),
    categories: z.array(categorieRef).default([]),
    chapoHtml: z.string().default(''),
    corpsHtml: z.string().default(''),
    notesHtml: z.string().default(''),
    extrait: z.string().default(''),
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
    titre: z.string(),
    date: z.coerce.date(),
    // Noms de catégories tels qu'ils apparaissent sur le site,
    // ex. ["Disques et représentations", "L'horrible Richard Wagner"]
    categories: z.array(z.string()).default([]),
    chapo: z.string().default(''),
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
    slug: z.string(),
    ordre: z.coerce.number().catch(999).default(999),
  }),
});

export const collections = { notules, nouvelles, corrections, categories };
