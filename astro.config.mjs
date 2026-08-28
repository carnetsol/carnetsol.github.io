import { defineConfig } from 'astro/config';
import sitemap from '@astrojs/sitemap';

/**
 * Liens sortants des notules écrites en Markdown.
 *
 * Le HTML hérité de Dotclear est traité par src/lib/liens.ts au moment du
 * rendu. Le Markdown, lui, ne passe jamais par là : il est converti par
 * la chaîne remark/rehype d'Astro. D'où ce petit greffon, écrit à la main
 * pour ne pas ajouter de dépendance (rehype-external-links ferait la même
 * chose, mais c'est un paquet de plus à installer et à maintenir).
 *
 * La liste des domaines internes est volontairement recopiée ici : le
 * fichier de configuration est chargé par Node avant toute compilation
 * TypeScript, il ne peut pas importer src/lib/liens.ts. Si vous ajoutez un
 * domaine, pensez aux DEUX endroits.
 */
const INTERNES = [
  'carnetsol.fr',
  'www.carnetsol.fr',
  'carnetsol.netlify.app',
  'carnetsol.github.io',
];

function liensSortants() {
  return (arbre) => {
    const parcourir = (noeud) => {
      if (noeud.type === 'element' && noeud.tagName === 'a') {
        const href = String(noeud.properties?.href ?? '');
        const m = href.match(/^https?:\/\/([^/:?#]+)/i);
        if (m && !INTERNES.includes(m[1].toLowerCase()) && !noeud.properties.target) {
          noeud.properties.target = '_blank';
          noeud.properties.rel = ['noopener', 'noreferrer'];
        }
      }
      for (const enfant of noeud.children ?? []) parcourir(enfant);
    };
    parcourir(arbre);
  };
}

export default defineConfig({
  site: 'https://carnetsol.fr',
  output: 'static',
  trailingSlash: 'always',
  integrations: [sitemap()],

  markdown: {
    rehypePlugins: [liensSortants],
  },

  // Pas de `base` : un seul projet sert les deux niveaux du site.
  //   /              -> le fil des notules (double de /css/)
  //   /css/          -> le fil des notules (adresse canonique)
  //   /css/AAAA/MM/JJ/ID-slug/  -> permalien identique à celui de Dotclear

  build: {
    // Une page = un dossier + index.html : les anciens permaliens
    // fonctionnent tels quels sur n'importe quel hébergement statique.
    format: 'directory',
  },
});
