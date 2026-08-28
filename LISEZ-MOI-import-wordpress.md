# Import du WordPress « Carnets sur sol (boueux) »

22 notules, catégorie **Carnets sur sol (boueux)**, identifiants 94001 à 94022.

## Marche à suivre

Dézippez à la racine du projet, puis, depuis cette même racine :

```powershell
python scripts\importer_wordpress.py "chemin\vers\carnetssursolboueux_WordPress_2026-08-27.xml"
```

La simulation n'écrit rien : elle liste les billets retenus, signale la
catégorie à créer et compte les images. Quand la liste vous convient :

```powershell
python scripts\importer_wordpress.py "chemin\vers\export.xml" --ecrire
npm run build
```

## Ce que fait le script

- **Catégorie créée automatiquement** dans `categories.json` si elle manque,
  sous le slug `carnets-sur-sol-boueux`, en recopiant la forme des entrées
  existantes.
- **Identifiants 94001+**, dans la continuité du plan : 92000 pour « 1 jour
  1 opéra », 93000 réservé aux disques, 94000 pour les boueux. Comme pour
  l'import Twitter, le script relit les notules existantes et glisse jusqu'au
  premier identifiant libre.
- **Adresses WordPress conservées** pour les 503 images, comme demandé. Rien
  n'est téléchargé.
- **Balisage Gutenberg nettoyé**, mais vos réglages conservés. Les
  commentaires `<!-- wp:image -->` disparaissent et les classes `wp-block-*`
  deviennent `illustration` / `legende`, avec `alignleft`, `alignright` et
  `aligncenter` préservées. Les largeurs choisies dans chaque article
  (`style="width:443px"`) restent intactes : le débordement est traité par un
  `max-width` dans la feuille de style, qui prime sur un `width` en ligne sans
  qu'on ait à le retirer.
- **Chargement différé** sur toutes les images. Certaines notules en comptent
  65 : sans cela, la page serait interminable à l'ouverture.
- **Liens internes réécrits.** Cinq billets se citent entre eux ; leurs
  adresses `carnetsol.wordpress.com` pointent désormais vers les nouvelles
  adresses `/css/`. Trois renvois qui étaient des cartes d'aperçu WordPress
  sont devenus de simples liens.
- **Vidéos YouTube** converties en `iframe` sans cookies.
- **50 légendes** conservées.
- **Deux commentaires** récupérés, tous deux sur « Le ru de Chaton » : celui
  de Golisande et votre réponse sous Belle Hémiole. Les sept rétroliens
  automatiques sont écartés.
- **Bandeau** « Initialement publié sur le site alternatif Carnets sur sol
  (boueux) », classe `.recuperation`, la même qu'après le crash de 2025. Il se
  règle par `--bandeau`, où `{blog}` reprend le titre du blog.

## Ce qui n'a pas été importé

**Les 19 brouillons.** Ils vont de « Rita Strohl » à « La Libération et les
menteurs », plus un sans titre du 24 juillet 2026. Le script les écarte par
défaut, comme la migration Dotclear écartait les notules non publiées.
`--brouillons` les inclurait, mais ils seraient alors publiés en ligne : à
n'employer qu'après relecture.

## Deux points à savoir

**Trois images ne viennent pas de WordPress** : elles sont hébergées sur
Google Photos (`lh3.googleusercontent.com`). Ces adresses expirent en général
au bout de quelques mois. Elles seront à reprendre lors du rapatriement des
médias.

**Les champs `importee` et `source`** que le script écrit dans chaque JSON
seront silencieusement retirés par le schéma Zod, qui ne les déclare pas. Ils
restent lisibles dans le fichier, mais pas dans vos gabarits Astro. Si vous
voulez les exploiter, ajoutez-les à `content.config.ts`.

## Style

Les classes `figure.illustration` et `figure.video` sont les mêmes que pour
l'import Twitter. Si vous ne les avez pas encore ajoutées à `style.css` :

```css
.notule-corps figure.illustration { max-width: 100%; margin: 1.2em 0;
                                   text-align: center; }
.notule-corps figure.illustration img { max-width: 100%; height: auto; }
.notule-corps figure.illustration.alignleft  { float: left;  margin: .4em 1.4em .8em 0; }
.notule-corps figure.illustration.alignright { float: right; margin: .4em 0 .8em 1.4em; }
.notule-corps figure.illustration.aligncenter { margin-left: auto; margin-right: auto; }
.notule-corps .legende { font-family: "Lucida Grande", Verdana, sans-serif;
                         font-size: .8em; color: var(--muted); }
.notule-corps figure.video { position: relative; padding-bottom: 56.25%; height: 0; margin: 1.2em 0; }
.notule-corps figure.video iframe { position: absolute; inset: 0; width: 100%; height: 100%; }
.notule-corps .renvoi { font-style: italic; }

@media (max-width: 600px) {
  .notule-corps figure.illustration.alignleft,
  .notule-corps figure.illustration.alignright { float: none; margin: 1.2em auto; }
}
```

Le `text-align: center` est ce qui manquait : une `figure` occupe toute la
largeur, et l'image, restée en flux, se collait à gauche. Il n'a aucun effet
sur les figures flottantes, qui se rétractent à la taille de leur contenu.

Le `max-width: 100%` est la pièce maîtresse : il l'emporte toujours sur un
`width` en ligne, donc vos 443 px sont respectés tant que la colonne est assez
large, et l'image se réduit d'elle-même en dessous. La requête média annule les
flottants sur petit écran, où ils seraient illisibles.

## Les six sites

Le script n'a rien de propre aux boueux. Depuis la racine du projet, en
adaptant le chemin des exports :

```powershell
$D = "$env:USERPROFILE\Downloads"

python scripts\importer_wordpress.py "$D\carnetssursolboueux.WordPress.2026-08-27.xml" --ecrire `
  --categorie "Carnets sur sol (boueux)" --postid-depart 94001 `
  --bandeau "Initialement publié sur le site alternatif {blog}"

python scripts\importer_wordpress.py "$D\carnetssursoldisques.WordPress.2026-08-27.xml" --ecrire `
  --categorie "Carnets sur sol (disques)" --postid-depart 93001 `
  --bandeau "Initialement publié sur le site alternatif {blog}"

python scripts\importer_wordpress.py "$D\carnetssursolnotules.WordPress.2026-08-27.xml" --ecrire `
  --categorie "Carnets sur sol (notules)" --postid-depart 95001 `
  --bandeau "Initialement publié sur le site alternatif {blog}"

python scripts\importer_wordpress.py "$D\carnetssursolconcerts.WordPress.2026-08-27.xml" --ecrire `
  --categorie "Carnets sur sol (concerts)" --postid-depart 96001 `
  --bandeau "Initialement publié sur le site alternatif {blog}"

python scripts\importer_wordpress.py "$D\1jour1opra.WordPress.2026-08-27.xml" --ecrire `
  --categorie "1 jour, 1 opéra" --postid-depart 92016 `
  --bandeau "Initialement publié sur le site thématique « {blog} »"

python scripts\importer_wordpress.py "$D\bellehmiole.WordPress.2026-08-27.xml" --ecrire `
  --categorie "Belle Hémiole" --postid-depart 97001 `
  --bandeau "Initialement publié sur Belle Hémiole, le carnet où je cache mes humeurs extra-musicales"
```

`{blog}` reprend le titre déclaré dans l'export. Pour Belle Hémiole, la phrase
est écrite en toutes lettres, l'export s'intitulant « Belle hémiole » sans
majuscule.

### Plages d'identifiants

| Plage | Site |
|---|---|
| 92001-92015 | 1 jour 1 opéra (fil X/Twitter) |
| 92016+ | 1 jour, 1 opéra (WordPress) |
| 93001+ | Carnets sur sol (disques) |
| 94001+ | Carnets sur sol (boueux) |
| 95001+ | Carnets sur sol (notules) |
| 96001+ | Carnets sur sol (concerts) |
| 97001+ | Belle Hémiole |

### Doublons

Un billet dont le jour est déjà occupé par une notule de la même catégorie est
écarté et signalé. La comparaison porte sur la journée, pas sur le billet :
certains blogs publient plusieurs fois le même jour (quatre billets le
16 septembre 2024 aux concerts). Cela rend un réimport sans danger, mais
impose `--forcer-doublons` pour une récupération ciblée.

Rien n'est écarté au sein d'une même exécution : la liste des journées prises
est figée au démarrage.

Pour Kaunas, importez le WordPress « 1 jour, 1 opéra » **avant** le fil
X/Twitter : le script du fil n'ayant pas de détection par date, les deux
versions coexisteront et vous choisirez ensuite.

### Récupérer un billet d'une ancienne sauvegarde

Un export plus ancien peut contenir des billets supprimés depuis. Pour ne
reprendre que ceux-là, sans réimporter le reste :

```powershell
python scripts\importer_wordpress.py "$D\carnetssursolconcerts.WordPress.2025-04-17.xml" --ecrire `
  --categorie "Carnets sur sol (concerts)" --postid-depart 96001 `
  --bandeau "Initialement publié sur le site alternatif {blog}" `
  --seulement "2025-04-11,2025-04-17" --forcer-doublons
```

`--seulement` restreint aux journées indiquées. `--forcer-doublons` est
nécessaire ici : la détection raisonne par journée, et si le nouvel export
contient un autre billet le même jour, la récupération serait écartée à tort.
Les identifiants se placent d'eux-mêmes après ceux déjà pris.

Pour comparer deux exports du même site :

```powershell
python -c "import xml.etree.ElementTree as ET,sys;n={'wp':'http://wordpress.org/export/1.2/'};g=lambda f:{(i.findtext('wp:post_date',namespaces=n) or '')[:10]+' '+(i.findtext('title') or '') for i in ET.parse(f).getroot().findall('./channel/item') if i.findtext('wp:post_type',namespaces=n)=='post'};a=g(sys.argv[1]);b=g(sys.argv[2]);print('Dans l ancien seulement :');[print(' ',x) for x in sorted(a-b)] or print('  (aucun)')" ANCIEN.xml RECENT.xml
```

### Volumes attendus

| Site | Publiés | Écartés | Images | Commentaires |
|---|---|---|---|---|
| boueux | 22 | 19 | 503 | 2 |
| disques | 48 | 11 | 444 | 0 |
| notules | 5 | 9 | 11 | 0 |
| concerts | 54 | 16 | 343 | 38 |
| 1 jour, 1 opéra | 36 | 1 | 143 | 0 |
| Belle Hémiole | 6 | 9 | 1 | 1 |

Soit 171 notules et 1 445 images, toutes servies depuis WordPress.
