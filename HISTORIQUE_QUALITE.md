# Relevés de qualité datés

Le cycle principal conserve les valeurs réellement lues dans « Data Quality & KPI »
après sa mise à jour. Un nouvel onglet « Historique qualité » contient une ligne
par jour d'observation (Europe/Paris) et indicateur. La même ligne est actualisée
pendant la journée ; les jours passés ne sont pas remplacés.

Colonnes : clé technique, date du relevé, horodatage UTC, dimension, indicateur,
valeur, définition et total de référence. Zéro et valeur absente sont distincts.
L'historique reprend aussi les totaux publiés, sans les déduire du texte.

Les écritures passent par le moteur et le verrou existants. Les clés sont relues
avant des écritures sur plages explicites : aucun append aveugle en cas de reprise.
Un schéma, doublon, horodatage ou rejeu antérieur incohérent arrête la sauvegarde.
L'enregistrement est activé par PMU_KPI_HISTORY=true uniquement pour le cycle
principal, pas à chaque cheval, pour limiter les accès et la taille du registre.

La conservation commence à l'activation ; aucun relevé passé n'est inventé.
Un relevé quotidien est la dernière observation disponible, pas nécessairement
une mesure effectuée à minuit. Le jour en cours reste provisoire.

Dans TROT Analytics, cette chronologie est séparée de la qualité actuelle des
courses regroupées par date de course. Ces deux lectures ont des significations
différentes. Il faut au moins deux jours d'observation pour une courbe temporelle.
