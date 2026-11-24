# Colonnes publiées : mise à niveau du 16 novembre 2026

Le registre utilise toujours le même moteur de publication et le verrou commun
`pmu-donnees-production`. Le retrait physique a lieu pendant la synchronisation
globale (`allow_structure=True`) ; les publications individuelles ne déplacent
pas les colonnes. Les en-têtes sont relus après suppression, en ordre décroissant
d'index, puis les mises à jour utilisent les nouvelles positions.

## Retraits de l'affichage

- Courses & Prévisions : `ml_proba_podium` (aucune calibration disponible),
  `synthese_actualite` (ancienne synthèse multisources, redondante avec PMU),
  `divergences_sources` (restes des comparaisons Equidia/ZEturf).
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

## Matching direct et ML

Deux colonnes numériques supplémentaires sont ajoutées à Résultats & Analyse (15 → 17) : `matching_direct_pct` et `matching_ml_pct`. Chaque taux représente le nombre de chevaux distincts retrouvés dans le podium divisé par trois, exprimé sur 100 et arrondi à deux décimales. Une preuve manquante ou chronologiquement invalide laisse la cellule vide ; 0 est un score réel. Aucun pronostic historique n'est recalculé.

## Cotes PMU pré-départ

La valeur, l'heure de collecte et l'heure du rapport PMU sont publiées dans
`top3_cotes_valeur`, `cote_releve_utc` et `cote_rapport_utc`. Une cote
conservée après un incident garde ses horodatages. Les non-partants ont des
cellules de cote et de sélection vides.

La sélection de marché publie ses propres rangs, son état et son heure de
calcul. Trois cotes suffisent à proposer un TOP3 partiel. L'état complet
requiert une liste complète et une cote pour chaque cheval éligible.
La section « Cotes PMU » mesure la couverture, la fraîcheur et les TOP3
complets à partir du jour J. Le contrôle de consolidation compare les
valeurs publiées aux fichiers du collecteur.

## Identités et horodatages opérationnels

Le TOP3, le nom du gagnant potentiel et le podium partagent la jointure par
clé de course et numéro PMU. Le nom d'un intervenant enregistré dans un ancien
pronostic ML ne constitue pas une preuve d'identité. Les conclusions de
l'onglet Résultats & Analyse comparent les matchings Direct et ML publiés.
Le TOP3 Cotes de l'onglet Courses & Prévisions reste disponible séparément.

Les nouveaux horodatages opérationnels écrits dans Sheets sont en ISO 8601
avec décalage explicite. Le départ prévu est exprimé en Europe/Paris. Les
colonnes UTC sont exprimées en UTC. Les séries numériques déjà publiées sont
relues dans le fuseau indiqué par leur colonne. Un horaire local ambigu au
changement d'heure nécessite une source avec décalage explicite. Les dates
civiles gardent leur format natif Sheets. Les colonnes de consultation
« Paris · … » affichent les instants sous forme de dates Sheets natives
(`dd/mm/yyyy hh:mm`). Les colonnes sources restent disponibles aux consommateurs
du registre et sont masquées. Les champs composites affichent le même lien avec
le relevé en heure de Paris. Les valeurs d’horodatage dans les colonnes KPI
mixtes possèdent un format par cellule. Les libellés KPI historiques restent
les identifiants des relevés et la note indique le fuseau d’affichage.
Streamlit affiche le départ prévu et l'heure de lecture de l'arrivée à Paris. Cette dernière correspond à la
lecture des rangs dans le flux participants. Pour les nouvelles arrivées, le
podium lu doit concorder avec le podium déclaré définitif par le programme
PMU. Le programme fournit ce statut sans heure de proclamation officielle.
