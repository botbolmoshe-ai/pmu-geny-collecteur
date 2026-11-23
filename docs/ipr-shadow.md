# IPR en mode observation

Le workflow de production réutilise le relevé PMU déjà chargé et les fiches Geny présentes dans le cache. Le flag GitHub Actions `IPR_SHADOW_ENABLED=false` suspend calcul, synchronisation IPR et certification. Les observations et leurs preuves restent consultables. Les écritures se limitent au circuit Sheets existant et au répertoire `ipr/` du cache.

## Score ipr-v1

Une sortie historique doit être disponible au moment du relevé, datée d'un jour antérieur, dans la même discipline, à une distance documentée et à 500 m au plus de la cible. Les dates ambiguës sont écartées. L'IPR utilise jusqu'à dix sorties dans les 365 derniers jours. La note d'une sortie est le rang ramené à l'effectif lorsqu'il est fourni, ou le barème ordinal documenté (5, 3,5, 2,5, 1,5, 1 point pour les cinq premières places) ramené à 100. Un DAI documenté compte comme une sortie à zéro. Un non-partant, une identité ambiguë ou une absence de sortie exploitable laissent le score vide.

La moyenne est pondérée par la récence, la distance, l'hippodrome, la grande/petite piste, le départ, la ferrure et le rapport d'allocations, selon les preuves disponibles. L'allocation est un indice de niveau du lot. Les poids sont des hypothèses fixes. La confiance descriptive dépend de l'échantillon effectif pondéré, de la couverture des six preuves complémentaires et du taux de DAI. Le nombre de sorties, la couverture, le statut et les motifs accompagnent le score.

## Publication et mesure

Les neuf colonnes IPR sont ajoutées à droite. Le statut d'usage contrôle l'italique des en-têtes et des cellules. Une note d'en-tête conserve la légende. Le registre présente la dernière version calculée avant départ. Une observation de préparation J+1 est signalée comme telle et ne constitue pas un TOP3 IPR. Seules les versions H-3/H-2 calculées dans la fenêtre et relues dans le registre avant le premier départ de la réunion sont figées pour l'évaluation prospective.

Le bilan glissant sur sept jours se trouve dans `ipr/bilan.json`. Il contient les détails par course, les segments, la fraîcheur, le taux de calcul, les champs manquants et l'écart de médiane entre semaines. Les comparaisons appariées exigent le même jalon, le même relevé, la même liste de partants et une arrivée PMU vérifiée. L'intervalle bootstrap porte sur les courses appariées.

Le rejeu `python -m scripts.audit_ipr --help` archive seulement les versions Git de `pmu-data` présentes avant la course. Il vérifie l'horodatage du relevé PMU et la disponibilité des fiches Geny. Les arrivées proviennent de la référence arrêtée. Le rejeu reste rétrospectif, même lorsque les données d'entrée sont attestées avant départ.
