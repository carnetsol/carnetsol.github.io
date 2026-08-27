# Corriger une notule d'archive

Les fichiers de `src/content/notules/` sont **régénérés** à chaque migration du
dump : les modifier à la main serait perdu. On dépose donc ici un correctif,
appliqué à la compilation, qui survit à toutes les régénérations.

## Comment faire

Créez un fichier `<postId>.json` dans ce dossier. L'identifiant est celui du
nom de fichier de la notule (`src/content/notules/1215.json` → `1215.json`).

### Corriger une coquille sans recopier le texte

```json
{
  "postId": 1215,
  "note": "Coquille signalée en commentaire",
  "remplacements": [
    { "chercher": "Erreur a corriger", "remplacer": "Passage rectifié" }
  ]
}
```

Chaque remplacement s'applique à **toutes** les occurrences, dans le corps et
le chapô. Ajoutez `"regex": true` pour utiliser une expression régulière.

### Remplacer un champ entier

```json
{
  "postId": 1215,
  "titre": "Le piano français, type et discographie",
  "chapoHtml": "<p>Un nouveau chapô.</p>"
}
```

Champs acceptés : `titre`, `chapoHtml`, `corpsHtml`, `notesHtml`, `extrait`,
`categories`, `date`.

### Les deux à la fois

Les remplacements de champs sont appliqués d'abord, les remplacements
chercher/remplacer ensuite — donc sur le texte déjà remplacé.

## Ce qu'un correctif ne fait pas

- Il ne change pas l'adresse de la notule : le permalien reste celui qu'ont
  indexé les moteurs depuis vingt ans.
- Il ne s'applique pas aux notules écrites en Markdown dans
  `src/content/nouvelles/` — celles-là, modifiez-les directement.
