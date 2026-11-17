# Colonnes publiées : mise à niveau du 16 novembre 2026

Le registre utilise toujours le même moteur de publication et le verrou commun
`pmu-donnees-production`. Le retrait physique a lieu pendant la synchronisation
globale (`allow_structure=True`) ; les publications individuelles ne déplacent
pas les colonnes. Les en-têtes sont relus après suppression, en ordre décroissant
d'index, puis les mises à jour utilisent les nouvelles positions.

## Retraits de l'affichage

- Courses & Prévisions : `ml_proba_podium` (aucune calibration disponible),
  `synthese_actualite` (ancienne synthèse multisources, redondante avec PMU),
  `divergences_sources` (restes des comparaisons Equidia/ZEturf),
  `top3_cotes_valeur`, `top3_cotes_top3`, `top3_cotes_statut`, `top3_cotes_utc`
  (aucune cote ni sélection effectivement publiée sur les lignes auditées).
- Historique chevaux : `rncn`, `nombre_partants`, `gains_course_eur`,
  `driver_jockey`, `entraineur`, `date_source` (champs hérités, sans alimentation
  régulière dans le collecteur historique actuel).
- Résultats & Analyse : `top3_cotes_numeros`, `score_cotes`,
  `analyse_comparative`, `derniere_sync_utc` (sorties absentes, comparaison
  incomplète ou date de publication produite seulement par les anciens exports).

Cela retire 17 colonnes : 51 → 44 dans Courses, 19 → 13 dans Historiques et
19 → 15 dans Résultats. Les colonnes allouées mais sans en-tête ne sont pas des
champs publiés. Les données brutes, les calculs de cotes, les expériences ML,
les anciennes prévisions et les instantanés restent conservés dans pmu-data.
Les colonnes retirées sont exclues de la source de publication et des ajouts
d'en-têtes ; elles ne sont pas recréées au passage suivant.

## Champs utiles conservés et corrigés

Les ferrures et chronos restent utiles malgré leurs lacunes. Les rangs,
sélections et scores ML sont conservés. Le statut distingue le candidat
expérimental actif du modèle promu ; un rejeu rétrospectif reste distinct des
prévisions effectivement enregistrées avant départ.

`extraction_utc` est alimenté par la date `extrait_utc` du document Geny,
normalisée en UTC, avec le libellé « Capture historique · UTC ». La date de
migration ou de synchronisation ne remplace jamais cette date source. Une
ancienne ligne hors des captures disponibles garde sa valeur existante.

Le rang individuel officiel est alimenté directement par les arrivées PMU,
même sans export ou manifeste Geny. Le statut ML est explicite sur chaque
bilan. Les libellés « PMU · État ferrure » et « PMU · Disponibilité avis/pronostic »
remplacent les anciens intitulés trop généraux.

Le KPI ML compte les sélections OUI, pas les simples rangs. Les références
résiduelles des deux anciennes lignes éditoriales sont effacées. Les formules
restantes suivent les déplacements natifs Google Sheets ; elles sont relues
après application.

Les mises à jour contiguës sont regroupées par colonne, sans écrire dans les
trous, pour publier les dates de capture sans multiplier les appels API.

## Vérification et sauvegarde

Une copie native Google Sheets et un export complet XLSX précèdent la migration.
Les tests vérifient les trois onglets, la conservation des clés et lignes, les
positions après retrait, le zéro numérique, les dates source, les arrivées,
les écritures groupées et l'absence de recréation au deuxième passage.
La fin d'un workflow ne suffit pas : contrôler les en-têtes, les formules, les
clés de performance et les comptages réels après publication.

## Matching direct et ML (17 novembre 2026)

Deux colonnes numériques supplémentaires sont ajoutées à Résultats & Analyse
(15 → 17) : `matching_direct_pct` et `matching_ml_pct`. Chaque taux est le
nombre de chevaux distincts retrouvés dans le podium vérifié divisé par trois,
exprimé sur 100 et arrondi à deux décimales. Les sélections absentes, incomplètes
ou sans horodatage valide avant départ ne sont pas notées. La comparaison ne
recalcule aucune sélection historique.
