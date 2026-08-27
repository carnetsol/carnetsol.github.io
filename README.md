# Carnets sur sol — site statique (Astro)

Reprise de `operacritiques.free.fr/css/` (Dotclear 1.2, thème Keepsake) sous
forme de site statique, archives comprises.

## Structure des adresses

| Adresse | Contenu |
|---|---|
| `/` | Menu principal : index, catégories, multimédia, archives |
| `/css/` | Le fil : les **15 dernières notules** + la boîte de recherche |
| `/css/AAAA/MM/JJ/<id>-<slug>/` | Une notule — **permalien identique à Dotclear** |
| `/css/recherche/` | Recherche plein texte (Pagefind) |
| `/css/rss.xml` | Flux RSS |
| `/archives/` | Toutes les notules, par année et par mois |
| `/categorie/` et `/categorie/<slug>/` | Les rubriques |

Les permaliens reproduisent exactement ceux de Dotclear : les milliers de liens
existants — y compris ceux que les notules se font entre elles — continuent de
fonctionner sans redirection.

## 1. Importer le dump

```bash
python3 scripts/migrate_dotclear.py dump.sql --out src/content --avec-commentaires
```

Options utiles :

- `--brouillons` : inclure aussi les notules non publiées (`post_pub = 0`)
- `--prefixe` : si les tables ne s'appellent pas `sursol_*`
- sans `--avec-commentaires`, seuls les compteurs sont conservés

Le script ne dépend d'aucun paquet externe et n'a pas besoin d'un serveur MySQL :
il tokenise directement les instructions `INSERT` du dump en respectant
l'échappement MySQL (apostrophes, antislashs, HTML contenant virgules et
parenthèses).

Ce qu'il produit :

```
src/content/notules/<post_id>.json   une notule par fichier
src/content/categories.json          l'arborescence des rubriques
public/redirects.json                table des anciennes URL (pour vérification)
```

### Encodage

Les colonnes du dump sont déclarées `latin1` alors que Dotclear y a écrit de
l'UTF-8. Selon la façon dont le dump a été produit, le texte peut ressortir
correct ou doublement encodé (`Ã©` au lieu de `é`). Le script détecte le cas et
ne répare que si des marqueurs de mojibake sont présents, pour ne pas abîmer
le texte déjà correct. **À vérifier sur quelques notules après import.**

### Ce qui est conservé

Le corps des notules reste du **HTML brut**, injecté avec `set:html`. Il n'est
pas converti en Markdown : la conversion casserait les lecteurs audio, les
tableaux, les notes et vingt ans de mises en forme accumulées.

## 2. Lancer le site

```bash
npm install
npm run dev      # http://localhost:4321
npm run build    # compile puis construit l'index de recherche
npm run preview
```

`npm run build` enchaîne `astro build` et `pagefind --site dist`. L'index de
recherche est construit au moment de la compilation : la recherche fonctionne
entièrement dans le navigateur, sans serveur ni base de données.

## 3. Anciennes adresses avec chaîne de requête

Dotclear utilisait des adresses du type `index.php?2006/07/04/273-slug`. La
partie utile vit dans la chaîne de requête, qu'aucune règle de redirection
d'hébergeur ne sait traiter. `src/pages/404.astro` contient donc un script qui
les rattrape côté navigateur et redirige vers le bon permalien — y compris pour
`?q=` (recherche) et `?Nom-De-Categorie`.

Pour que ce rattrapage fonctionne, l'hébergeur doit servir `404.html` sur les
adresses inconnues **en conservant la chaîne de requête** (c'est le comportement
par défaut de Netlify, Vercel et Cloudflare Pages).

## 4. Reste à faire

- Remplir `/multimedia/` et `/index-general/` (pages actuellement à l'état d'ébauche)
- Rapatrier les images et fichiers joints de l'ancien hébergement dans `public/`
- Décider du sort des commentaires : ils sont importés et affichés en lecture
  seule, mais peuvent être exclus en retirant `--avec-commentaires`
