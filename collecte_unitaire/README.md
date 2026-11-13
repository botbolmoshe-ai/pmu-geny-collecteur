# Chevaux déjà courus : collecte individuelle et chargement progressif

Branche de travail : `test/boucle-historiques-courus`. Aucun changement du code de `main`.

La file initiale comprend 163 chevaux distincts présents dans le Google Sheets, sans historique complet, dont la course a une arrivée PMU enregistrée et dont le dernier statut explicite est PARTANT. Les chevaux disqualifiés sont inclus ; les non-partants sont exclus. Marvina Bella est déjà collectée (19 performances, identité vérifiée par le test 43321181833) et commence directement par la sauvegarde/synchronisation.

Pour chaque cheval : nouveau sous-processus Python et nouveau navigateur ; résolution du lien exact à partir de la course si nécessaire ; extraction et validation de l'identité, du nombre de performances et des champs obligatoires ; checkpoint sur cette branche ; sauvegarde de l'historique complet dans `pmu-data` ; ajout/mise à jour idempotente dans les onglets existants Historique chevaux et Courses & Prévisions ; actualisation des KPI ; cheval suivant.

Les profils du jour et les prévisions passées ne sont pas réécrits. Une erreur Sheets n'entraîne pas de nouvelle consultation Geny : le fichier validé reste conservé et seule la synchronisation est reprise. Les erreurs ne sont pas des historiques complets. Les liens ambigus ne sont pas devinés.

Les appels sont espacés d'au moins 30 secondes après une extraction. Tout 403/429 impose 30 minutes sans nouvel accès Geny, pour toute la file. Les erreurs sont retentées au plus deux fois par passage et les synchronisations trois fois ; une relance reprend les éléments inachevés sans recommencer les réussites. Aucun renouvellement de navigateur n'est utilisé pour contourner un refus.

Le workflow utilise le verrou `pmu-donnees-production` pour empêcher un cycle habituel d'écraser les données pendant le chargement. Le premier passage etait borne a 210 minutes ; la reprise ciblee des 31 cas est bornee a 75 minutes, avec un timeout GitHub de 240 minutes. Si une source empêche de terminer, l'état reste `PARTIELLE_REPRENABLE` et le nombre de chevaux non synchronisés reste explicite. Lancer à nouveau le job reprend la file persistée.

Suivi durable : `etat.json` et `progression.csv` sur cette branche ; historiques dans `historiques/<id>/`. Les diagnostics détaillés sont conservés en artefacts GitHub. Les écritures Sheets utilisent le compte de service déjà configuré dans les secrets du dépôt ; aucune clé n'est enregistrée dans le code ni les journaux.
