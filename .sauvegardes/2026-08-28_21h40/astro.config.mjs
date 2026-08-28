import { defineConfig } from 'astro/config';
import sitemap from '@astrojs/sitemap';

export default defineConfig({
  site: 'https://carnetsol.fr',
  output: 'static',
  trailingSlash: 'always',
  integrations: [sitemap()],

  // Pas de `base` : un seul projet sert les deux niveaux du site.
  //   /              -> le menu principal (index, catégories, multimédia, archives)
  //   /css/          -> le fil des notules (15 dernières + recherche)
  //   /css/AAAA/MM/JJ/ID-slug/  -> permalien identique à celui de Dotclear

  build: {
    // Une page = un dossier + index.html : les anciens permaliens
    // fonctionnent tels quels sur n'importe quel hébergement statique.
    format: 'directory',
  },
});
