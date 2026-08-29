---
titre: "C'est le calme… avant le départ…"
date: 2026-08-27
postId: 3458
slug: "c-est-le-calme-avant-le-depart"
categories: ["Intendance"]
vignette: "/medias/vol_cygnes.png"
---

<p class="illustration"><center><img src="/medias/vol_cygnes.png" alt="Vol de cygnes" /></center></p>

<p>… car je suis en train de préparer des bilans écrits des séries vidéo – ça prend du temps, mais vu que c'est là que j'ai concentré le plus de valeur ajoutée informative ces derniers mois, plutôt que d'écrire des superficialités en notule, autant faire l'effort… – et surtout en train de migrer <em>Carnets sur sol</em> !</p>

<p>Comme vous l'avez remarqué, en plus du crash catastrophique de l'an dernier — Free m'avait bloqué mes droits, impossible de recréer à la base même à partir de la sauvegarde, j'ai tout essayé mille fois pendant un mois alors qu'ils avaient juste oublié d'appuyer sur un bouton. Et comme c'est <em>un seul</em> salarié qui s'occupe des pages personnelles, en gérant l'obsolescence organisée avec l'espoir que le maximum de pages finisse par disparaître, inutile de vous dire qu'il est inutile de demander, une fois qu'on a soupçonné la panne, à ce que l'on intervienne (je le fis cependant).</p>

<p>Free, chez qui j'avais simplement voulu faire un essai en ouvrant <em>Carnets sur sol</em>, un simple bac à sable pour tester ce mode de publication qui faisait fureur, est un assez horrible hébergeur comme vous savez : plantages à répétition (le serveur mutualisé où le site était hébergé a carrément cramé l'an passé et la puce qui permettait d'en récupérer le contenu aussi), entraves à l'exportation des données, aux redirections… et le pire de tout : on ne peut pas exporter correctement une sauvegarde. Le contenu en est corrompu, tous les accents (UTF-8, norme « universelle ») sont traduits en ISO (tous les caractères accentués deviennent illisibles, même ceux du français), avant d'être recodés en UTF-8 pour être bien sûr qu'on ne puisse pas faire de reconversion. J'ai passé une centaine d'heures à régler le problème, y compris en automatisant le processus. Comme j'ai cité beaucoup de systèmes linguistiques dans le site et utilisé plusieurs langages de code, il en restait à foison.</p>

<p>À cela s'ajoute que dans le code de Dotclear – mon logiciel de publication, à l'époque à la pointe, on était au début de la compétition avec Wordpress –, on voit très bien la superposition entre la syntaxe wiki disponible dans l'interface, le html propre codé à la main, ou plus bavard dans un éditeur visuel (de type WYSIWYG), les variations de norme au fil des évolutions technologiques (html5)… et le résultat ne s'incarne pas toujours de façon propre dans la sauvegarde.</p>

<p>Et puis, comme le monde est mal fait, quand on utilise des slashes ou des apostrophes de code (puisqu'il n'y a pas d'apostrophe typographique sur les claviers et qu'il n'est pas très recommandé de transcrire du traitement de texte en html), c'est mal interprété par les logiciels ensuite (ce sont des démarcations typiques pour les commandes de code), y compris par Dotclear lui-même en le réimportant.</p>

<p>Ajoutons que mon archive, au bout de plus de 20 ans de notules (3200 entrées environ), est beaucoup trop grosse pour ce qui est prévu dans le traitement des logiciels, et que les importations sur les serveurs, même payants, ou dans les LLMs pour aider au débogage, s'avèrent impossibles.</p>

<p>Arrivé sur Dotclear, j'ai réussi une fois à charger la vieille sauvegarde, mais les accents étaient en pagaille, la version corrigée n'était ensuite plus rechargeable, et je ne sais pourquoi, un changement dans l'apparence du site s'est révélée irréversible, toutes les colonnes restant coupées et bouleversées même en revenant à l'état antérieur.</p>

<p>La conversion en Wordpress (l'autre grand logiciel de publication, qui représente un nombre considérable de sites en ligne) n'est pas envisageable vu l'ancienneté de ma version de Dotclear, or ne je parviens pas à faire la mise à jour. Par ailleurs je trouve l'interface de Wordpress lourde, et je n'aime pas du tout son éditeur visuel qui force aux sauts de ligne étrange, le tout écrit dans son propre langage html modifié, qu'il faut sans cesse convertir pour pouvoir ensuite l'exporter.</p>

<p>Au bout de six mois d'essais réguliers et d'une à deux centaines d'heures passées en pure perte à patcher les incohérences sans jamais en arriver au bout, toujours rien ne fonctionne.</p>

<p>Or la situation se dégrade, le site en http (et non https, la nouvelle norme sécurisée) est bloqué sur un nombre croissant de navigateurs, et à présent que j'ai restauré une sauvegarde propre, plus j'écris ici, plus j'aurai à nouveau à faire des manipulations lorsque je devrai migrer, puisque l'export est structurellement vérolé.</p>

<p>C'est pourquoi j'ai tout jeté par-dessus bord : les bases de données m'ont vraiment déçu par leur instabilité, si elles sont corrompues les données sont difficilement exportables. Je me suis lancé dans la confection d'un site statique… et à ma grande surprise, non seulement on peut obtenir sensiblement les mêmes résultats – à part pour les commentaires, et n'en recevant plus beaucoup, je vais travailler à cette question le moment venu –, mais on a surtout la main absolue sur la structure, qu'il n'est pas si compliqué de changer en cours de route. Idéal pour faire des essais et classer mes projets.</p>

<p>Je me retrouve ainsi avec un site qui reprend l'intégralité des notules de <em>Carnets sur sol</em> avec une base saine exportable à volonté, et dans lequel je peux agréger tous les projets combinés de ces dernières années : les Wordpress 1 jour 1 opéra, Carnetsol-disques, Carnetsol-concerts, Carnetsol-BOUEUX, pourquoi pas Belle Hémiole…<br />
La divine surprise fut même qu'il est possible de récupérer les archives du crash de 2025, et que je dispose à nouveau de l'intégralité du corpus (dont la grande série de 2024-5 sur les déchiffrages et découvertes de l'année) !</p>

<p>Parmi les nouveautés dont je suis très content :<br />
¶ structure révisable à l'infini, selon l'évolution des besoins ;<br />
¶ possibilité d'avoir plus de mobilité entre les écrans, notamment de pouvoir dérouler les anciennes notules en bas de l'écran, ou de lire la notule suivante en cliquant ;<br />
¶ récupération automatique des vidéos YouTube, pour lesquelles j'écris des présentations détaillées et qui seront donc très bien dans le flux des notules, même pour ceux qui ne sont pas intéressés par la vidéo ;<br />
¶ index complet (enfin !), très facile d'usage pour retrouver l'une des 3500 notules ;<br />
¶ du fait de l'inclusion des anciens WordPress et des légendes YouTube, beaucoup moins de menus juxtaposés, l'interface est beaucoup plus épurée : une page d'accueil avec les dernières notules, l'index par date ou catégorie et l'agenda. C'est tout. Tout est inclus de façon souple sous forme de notule, avec des étiquettes qui mentionnent bien de quel site provient le contenu.</p>

<p>Voilà qui devrait faciliter l'organisation et l'accès aux différents contenus de CSS ! Je suis bien sûr preneur de retours d'utilisateurs. (Vu que le site est en html statique, les solutions pour installer des commentaires étaient lourdes et inesthétiques, surtout vu le peu que je reçois en public : il faut envoyer un courriel avec les liens présents en fin de notule.)</p>

<p><a href="http://operacritiques.free.fr/css/">http://operacritiques.free.fr/css/</a> restera opérationnel quelque temps, <a href="http://carnetsol.fr/css/">carnetsol.fr</a> qui y renvoyait va lui basculer vers <a href="https://carnetsol.github.io/">carnetsol.github.io</a>. Suivez donc <strong>carnetsol.fr</strong> !</p>
