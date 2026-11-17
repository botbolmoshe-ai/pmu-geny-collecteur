# Ferrage, mesure ML et indicateurs objectifs

La qualification du ferrage courant distingue le code reconnu, la convention
PMU pour le trot sans déclaration de déferrage, le code inconnu et l'absence de
donnée. Une valeur inconnue reste conservée en brut mais ne remplit plus un
critère considéré comme renseigné. Le statut apparaît dans la colonne existante
« PMU · État ferrure » ; aucune nouvelle colonne de partant n'est ajoutée.

Une contradiction historique est marquée sur la performance, comptée parmi les
ferrures à compléter et exclue des comparaisons de ferrage du score direct. Les
preuves contradictoires ne sont pas remplacées par une valeur inventée.

Chaque cycle ML mesure désormais les versions certifiées après publication
Sheets avant départ. L'arrivée doit être PMU, vérifiée après départ et disponible
à l'instant du calcul. Le SHA256 du document doit correspondre au certificat ;
une version archivée peut être retrouvée si un calcul ultérieur non publié a
remplacé le dernier fichier. Les deux TOP3 sont comparés sur les mêmes courses.
La chronologie d'entraînement du candidat expérimental est vérifiée.

Le rapport est `ml/performance_prospective.json` : effectif, moyennes sur trois,
écart apparié, trois sur trois, deux sur trois et rejets. Zéro course admissible
donne des moyennes vides, pas une performance supposée. Ces mesures ne se
confondent ni avec l'apprentissage ni avec le rejeu rétrospectif.

Le réentraînement sur nouveaux labels et la sélection existante par validation
chronologique sont conservés. Le test ne sert pas à choisir le modèle. Les
seuils de promotion restent en place ; aucun ajustement technique ne vaut
preuve d'amélioration. Le statut avant 20 h est désormais « promotion différée »
pour ne plus laisser croire que le candidat expérimental ne peut pas apprendre.

Les KPI possédés par le processus sont ajoutés une fois, sans toucher les lignes
personnelles : mesures ML prospectives, H-2/H-1 ouvertes, publiées à temps ou
dépassées sans preuve, captures complètes/partielles et rejets du dernier passage
explicitement horodaté. Les effectifs et les définitions restent visibles.

Validation locale : 391 tests réussis. La mesure prospective est vérifiée sur
des données de test contrôlées ; les chiffres de production dépendent des
certificats et arrivées effectivement présents.
