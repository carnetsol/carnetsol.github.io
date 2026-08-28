# Import du fil « Un jour, un opéra » en notules autonomes

15 notules, une par journée mentionnée, catégorie **1 jour 1 opéra**.

## Marche à suivre

Dézippez à la racine du projet, puis, depuis cette même racine :

```powershell
python scripts\importer_fil_1j1o.py                # simulation, rien n'est écrit
python scripts\importer_fil_1j1o.py --ecrire       # écrit les notules + rapatrie les médias
npm run build
```

La simulation affiche la liste des 15 journées avec leurs identifiants et
signale celles dont la date est à vérifier. Regardez-la avant `--ecrire`.

## Ce que fait le script

- **Identifiants 92001 à 92015.** Vos notules Dotclear s'arrêtent vers 3460 :
  aucune collision possible, ni sur les fichiers, ni sur les alias de permalien
  générés par `[...permalien].astro`.
- **Adresses** de la forme `/css/2022/01/10/92009-vienne-therese-raquin-tobias-picker/`,
  cohérentes avec le reste du site. Le script relit toutes les notules
  existantes et désambiguïse une adresse déjà prise plutôt que de créer un
  doublon.
- **Titres au modèle du WordPress** : « JJ/MM/AA : Nom, Œuvre (à Ville) ».
  Seul le patronyme est retenu, comme sur le site.
- **Bandeau** « Récupéré automatiquement du fil Twitter « 1 jour, 1 opéra » »,
  suivi de la date et du lien vers le fil. Classe `.recuperation`, déjà stylée
  chez vous depuis la récupération de 2025.
- **Médias rapatriés** dans `public/medias/1j1o/`, servis depuis `/medias/1j1o/`.
  Les adresses `pbs.twimg.com` peuvent disparaître sans préavis ; mieux vaut
  les copies locales. `--distant` conserve les adresses Twitter si vous
  préférez.
- **Faux italiques Twitter normalisés.** Le fil utilisait les blocs Unicode
  mathématiques (𝑇ℎ𝑒́𝑟𝑒̀𝑠𝑒 𝑅𝑎𝑞𝑢𝑖𝑛) et les petites capitales (Tᴏʙɪᴀs Pɪᴄᴋᴇʀ)
  pour simuler l'italique. Ces caractères sont introuvables par Pagefind et
  illisibles par les lecteurs d'écran : ils sont ramenés en `<em>` / `<strong>`
  et en texte normal.
- **Slug de catégorie** lu dans `src/content/categories.json`. S'il n'y trouve
  pas « 1 jour 1 opéra », il le signale et retombe sur `1-jour-1-opera` —
  auquel cas ajoutez la catégorie au fichier avant de reconstruire.

## Quatre notules à relire

Le script les signale dans la simulation et pose un second encart dans la
notule elle-même.

| Notule | Le fil dit | Retenu | Pourquoi |
|---|---|---|---|
| Umeå | mardi 4 février 2022 | 4 janvier 2022 | le 4 février était un vendredi ; images de janvier |
| Osnabrück | vendredi 7 février 2022 | 7 janvier 2022 | le 7 février était un lundi ; images de janvier |
| Theater an der Wien | lundi 7 janvier 2022 | 10 janvier 2022 | le 7 janvier était un vendredi ; images postérieures à Osnabrück |
| Tel-Aviv | *(en-tête absent)* | 7 juin 2021 | Thread Reader a perdu le tweet d'ouverture ; images de la veille d'Astana |

Si vous tranchez autrement, corrigez le champ `date` dans `JOURNEES`, en haut
du script, et relancez.

## Deux points de style à regarder au premier build

Les classes `figure.illustration` et `figure.video` n'existent peut-être pas
encore dans votre `style.css`. Sans elles, les images s'afficheront en pleine
largeur brute et les iframes YouTube déborderont sur mobile. De quoi les
cadrer :

```css
.notule-corps figure.illustration { margin: 1.2em 0; text-align: center; }
.notule-corps figure.illustration img,
.notule-corps figure.illustration video { max-width: 100%; height: auto; }
.notule-corps figure.video { position: relative; padding-bottom: 56.25%; height: 0; margin: 1.2em 0; }
.notule-corps figure.video iframe { position: absolute; inset: 0; width: 100%; height: 100%; }
.motdiese { color: var(--muted); }
```

## Poids

Environ 90 images et 5 courtes vidéos. Comptez quelques dizaines de mégaoctets
dans `public/medias/1j1o/` — sans commune mesure avec la limite Netlify, mais
c'est autant à pousser sur GitHub au premier commit.


## Deux titres à valider

**Tel-Aviv (92002).** Le fil ne nomme pas l'ouvrage — le tweet d'ouverture
manque — et il y est surtout question de la maison elle-même. D'où un titre
réduit : « 07/06/21 : Sebba (à Tel-Aviv) ». À compléter si vous retrouvez
l'œuvre.

**Violet (92014).** Le fil situe la représentation à la Scène de Recherche de
l'ENS Paris-Saclay, sans nommer de commune. J'ai donc écrit « (à l'ENS
Paris-Saclay) » plutôt que de trancher entre Cachan, l'ancien campus, et
Gif-sur-Yvette, où l'école est installée depuis 2020.
