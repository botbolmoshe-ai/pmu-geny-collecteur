# Évaluation des variables Geny

Le premier essai utilise `pmu-data@3553188`, avec une coupure au 24 novembre
2026 à 17 h UTC. Il reste 90 courses et 1 197 partants après contrôle des
captures et des arrivées. La validation est effectuée à l'échelle de la
course, avec les mêmes partants pour chaque référence et son candidat.

| Méthode | Courses appariées | Chevaux du podium retrouvés par la référence | Par le candidat |
| --- | ---: | ---: | ---: |
| Direct | 19 | 17 | 17 |
| ML logistique | 17 | 16 | 14 |
| IPR | 0 | — | — |

L'écart ML est de −0,118 cheval retrouvé par course, avec un intervalle
bootstrap apparié à 95 % de [−0,294 ; 0]. Il n'y a aucune course commune aux
trois méthodes. Le rejeu Direct et le rejeu IPR exigent le même instant
d'observation et les mêmes partants que la capture ML. Ce bilan mesure les
candidats sur archives, sans attester une publication de ces candidats.

Le tandem cheval–driver et la forme en autostart sont calculables sur
respectivement 51 et 13 partants. Le chrono sur parcours et la forme sur
parcours ou par niveau d'allocation sont absents des observations
rétrospectives admissibles. Ces variables exigent le contexte de la course
daté avant le relevé, et des sorties comparables du même cheval. Les nouveaux
relevés calculent ces variables directement à partir du contexte disponible.
L'allocation historique sert de proxy du niveau. Le chrono est la médiane de
sorties classées, sur le même hippodrome, le même parcours et une distance
proche. Le départ historique doit porter la mention explicite Auto.
La corde, le terrain brut et la catégorie ne sont pas exploités dans ce
premier essai. Les cotes et les champs techniques sont hors variables.

L'identité Geny doit être vérifiée, la capture historique antérieure au
relevé et les sorties au plus tard la veille. Les dates ambiguës sont
écartées et un signal demande au moins deux sorties admissibles. Les
captures existantes peuvent être rejouées uniquement si le document Geny
correspond à la source et à l'horodatage inscrits dans la capture. Pour le ML,
chaque journée de test utilise un entraînement sur les jours précédents et
des arrivées déjà vérifiées au début du test.

Les nouvelles prévisions Direct et IPR peuvent archiver un
`candidat_geny` à côté de leur classement. Le ML enregistre les signaux dans
ses nouveaux relevés pour entraînement et comparaison hors ligne. Les
listes de variables des modèles en service et les TOP3 publiés restent
inchangés. Ce premier résultat ne justifie aucune promotion.

Reproduire le bilan hors réseau depuis la racine du dépôt

```bash
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 python -m pmu_geny.evaluation_geny \
  --cache /chemin/vers/pmu-data --coupure 2026-11-24T17:00:00Z
```
