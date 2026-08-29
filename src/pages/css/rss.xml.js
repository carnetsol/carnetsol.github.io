import rss from '@astrojs/rss';
import { getCollection } from 'astro:content';
import { notulesPourListe } from '../../lib/notules';
import { texteLisible } from '../../lib/texte';

export async function GET(context) {
  const notules = await notulesPourListe();
  const dernieres = notules
    .sort((a, b) => b.data.date.valueOf() - a.data.date.valueOf())
    .slice(0, 30);

  return rss({
    title: 'Carnets sur sol',
    description: "Notules d'opéra, de disques et de promenades — depuis 2004.",
    site: context.site,
    customData: '<language>fr-FR</language>',
    items: dernieres.map((n) => ({
      title: n.data.titre,
      link: n.data.url,
      pubDate: n.data.date,
      description: texteLisible(n.data.extrait),
      content: n.data.chapoHtml || n.data.corpsHtml,
      categories: n.data.categories.map((c) => c.nom),
    })),
  });
}
