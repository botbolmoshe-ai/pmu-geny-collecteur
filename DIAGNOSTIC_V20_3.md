# V20.3 — Diagnostic de découverte PMU

Correction ciblée de la découverte : lecture des codes pays sur réunion **et** hippodrome, compteurs d’exclusion par motif, journal explicite et diagnostic persistant.

## Vérification
- Lancer Actions → PMU V20.3 → mode `auto`.
- Ouvrir l’étape « Cycle automatique quotidien ».
- Chercher la ligne `DIAGNOSTIC_PMU`.
- Sur la branche `pmu-data`, inspecter `sources_pmu/diagnostic_YYYY-MM-DD.json`.

Un retour `ZERO_COURSE_A_DIAGNOSTIQUER` ne constitue pas une collecte réussie. Un retour `ERREUR_COLLECTE` indique que la requête ou son décodage a échoué.

**Limite :** l’API PMU ne peut pas être appelée depuis le conteneur de préparation ; le correctif est testé hors ligne avec des données de test, pas vérifié sur le schéma live du jour.
