# Fiche technique de mon chatbot

## Le modèle et les prix

Le chatbot utilise le modèle claude-opus-5-5 d'Anthropic, appelé avec la bibliothèque Python anthropic.
Les prix sont exprimés en dollars pour un million de tokens :
- 4 dollars pour les tokens envoyés (l'historique, la consigne, les images) ;
- 20 dollars pour les tokens écrits par Claude, réflexion comprise ;
- 0,20 dollar pour les tokens relus depuis le cache ;
- 5 dollars pour les tokens mis en cache.
Le cache permet de ne pas repayer plein tarif tout l'historique à chaque message.

## La clé API

La clé API est rangée dans une variable d'environnement Windows nommée ANTHROPIC_API_KEY.
Elle n'est écrite dans aucun fichier du projet. En ligne, elle est stockée dans les Secrets de Streamlit.
Pour l'afficher dans le terminal de VS Code, on tape :
[Environment]::GetEnvironmentVariable('ANTHROPIC_API_KEY','User')

## La mémoire

Claude ne se souvient de rien entre deux appels. C'est le programme qui garde la liste des messages,
appelée historique, et qui la renvoie en entier à chaque nouveau message. Chaque tour ajoute deux éléments :
la question de l'utilisateur (rôle user) et la réponse de Claude (rôle assistant).

## Les outils

Claude dispose de quatre outils : heure_actuelle, calculer, lancer_de et chercher_documents.
Quand il demande un outil, le programme exécute la fonction Python correspondante puis lui renvoie le résultat.
La boucle continue tant que la réponse de Claude se termine par la raison tool_use.

## Les personnalités

Quatre personnalités sont proposées : Amoureux (couleur rose), Prof patient (bleu), Pirate (orange)
et Assistant normal (vert). La personnalité est une consigne cachée envoyée dans le paramètre system.

## La mise en ligne

Le code est sur GitHub dans le dépôt privé Cyriacccc/mon-chatbot, sur la branche main.
Le site est hébergé gratuitement par Streamlit Community Cloud, qui se met à jour à chaque envoi sur GitHub.
Le site est protégé par un mot de passe défini dans le secret MOT_DE_PASSE.

## Le compteur de dépenses

Le total des dépenses et le budget sont enregistrés dans la table chatbot_reglages d'une base Supabase.
Sur l'ordinateur, sans Supabase, ils sont enregistrés dans le fichier reglages.json.
La jauge est verte en dessous de 60 % du budget, orange entre 60 et 85 %, et rouge au-delà.
