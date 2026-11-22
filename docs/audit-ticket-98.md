# Ticket 98 — référence avant déploiement

## Production sur 48 heures

Fenêtre UTC du 19 novembre 2026 à 21 h 46 au 21 novembre 2026 à 21 h 46. Les runs sont comptés selon leur création. Les écritures Sheets sont comptées à la date du contrôle confirmé, à partir des checkpoints de `pmu-data` arrêtés sur `97a275aa`.

| Workflow | Exécutions | Étapes de collecte ou inventaire exécutées | Durée cumulée de ces étapes |
|---|---:|---:|---:|
| Incrémental | 25 réussites | 9 exécutées, 16 sautées | 38 min 23 s |
| Rattrapage global | 1 réussite manuelle | 1 exécutée | 7 s |
| Production PMU | 24 réussites et 3 échecs | | |

Pour l’incrémental, le délai médian entre la création du run et le démarrage du job était de 3 s, avec un maximum de 5 s. Ce délai exclut le retard entre le cron et la création du run. La durée d’étape comprend la collecte et les synchronisations, et ne mesure pas le temps réseau Geny. Les journaux de jobs accessibles via la CLI étaient vides lors de l’audit.

- Les checkpoints de l’incrémental attestent **86 carrières complètes distinctes** et **1 965 ajouts de performances recontrôlés dans Sheets**, soit 43 carrières et 982,5 lignes par 24 h sur la fenêtre. Les 86 contrôles historiques n’ont relevé aucun doublon de valeur après écriture.
- Le rattrapage global n’a produit aucune nouvelle synchronisation historique confirmée durant cette fenêtre. Son bilan du 20 novembre à 15 h 27 UTC donne **1 174 cibles complétées sur 2 584**, **1 410 restantes**, **479 historiques à enrichir en ferrures** et **72 carrières du lot initial sur 96 publiées**. Les cibles d’inventaire peuvent représenter plusieurs contextes d’un même cheval.
- Le journal durable atteste **cinq refus 403 et un refus 429** entre le 19 novembre à 23 h 48 et le 20 novembre à 14 h 03 UTC. Le collecteur applique une pause commune de 30 minutes. Les états ne donnent pas un décompte exhaustif des décisions de pause ni des quotas Sheets consommés.
- Une carrière acceptée peut réutiliser une capture persistée. Les 86 carrières sont mesurées sur les états synchronisés. Les archives et les acquisitions réseau inédites ne sont pas dénombrées par cette mesure.

[Runs incrémentaux](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/actions/workflows/historiques-incrementaux.yml) · [Run de rattrapage](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/actions/runs/44763420602) · [État durable](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/tree/97a275aa)

## Validation TOP3 hors échantillon

Rejeu en lecture seule des captures pré-départ du même checkpoint. Apprentissage sur 114 courses jusqu’au 19 novembre, validation sur 5 courses le 20, puis test sur 23 courses le 21. Les dates disjointes séparent également les réunions. Les étiquettes d’apprentissage et de validation sont filtrées à l’instant admissible suivant. Les cotes sont exclues des variables. Le gradient boosting a été retenu sur la validation.

| Méthode | Courses comparables | Chevaux du podium retrouvés | Moyenne sur 3 |
|---|---:|---:|---:|
| Forme PMU au même relevé | 21 | 18 | 0,857 |
| Gradient boosting | 21 | 18 | 0,857 |
| Hybride à rangs de même poids | 21 | 14 | 0,667 |

Écarts appariés par rapport à la forme PMU au même relevé. ML **0,000** avec IC bootstrap à 95 % de **−0,381 à +0,429**. Hybride **−0,190** avec IC de **−0,524 à +0,095**. Sur l’ensemble des 23 courses, le ML retrouve 20 chevaux du podium. La preuve du TOP3 Direct publié et issu du même relevé manque sur ce test, ce qui borne la comparaison à la forme PMU capturée. L’échantillon ne démontre aucun gain robuste. Le rapport produit par la commande comprend aussi la ventilation attelé et monté.

```bash
python -m pmu_geny.experience_ml --cache /chemin/vers/pmu-data \
  --sortie /tmp/pmu-98-experience --validation 2026-11-20 --test 2026-11-21
```


## Apport de Crack confirmé et Haut potentiel

Rejeu en lecture seule sur `pmu-data@69d1ed053b6c6889e75c3d69116c82e339972eab`
avec la même commande et le même découpage chronologique. Le rapport
`profils_partants` distingue l'ajout de chaque signal et leur combinaison.

- **Direct.** 17 courses avec version Direct horodatée, certifiée et relue
  dans Sheets avant départ, et liste de partants concordante avec le jeu test.
  Aucun signal positif. Les quatre variantes retrouvent 19 chevaux du podium
  sur 51 places possibles et aucune sélection ne change.
- **ML.** Les deux états sont absents des captures de cette période
  sur 1 517 partants d'entraînement, 58 de validation et 303 de test.
  La référence retrouve 20 chevaux du podium sur 69 places possibles.
  Les trois variantes sont classées « données insuffisantes ».

Les nouvelles captures enregistrent les états à l'observation pré-départ.
Une comparaison concluante nécessite des exemples positifs et négatifs dans
les différentes périodes. Les archives existantes servent d'entrée en
lecture seule et aucune variante de profils n'est promue par ce rapport.

## Incident de reprise du 20 au 22 novembre

Les 26 exécutions pertinentes visibles, dont 25 incrémentales et un
rattrapage manuel, ont toutes conclu avec succès. L'étape de collecte
incrémentale n'a été exécutée que neuf fois. Les journaux de ces passages
comptent 69 captures complètes validées le 20, puis aucune dans les deux
recettes nocturnes du 21. Ce compteur inclut les captures validées par le
moteur et se lit indépendamment des ajouts Sheets.

- Le rattrapage manuel du 20 a cédé la priorité au PMU. Le premier
  passage nocturne du 21, à 22 h 31 UTC, a hérité d'une entrée Actions
  périmée. La PR #100 a corrigé ce premier blocage.
- Le passage suivant a reçu un refus Geny 429 à 22 h 35 UTC. La pause
  était applicable jusqu'à 23 h 05 min 43 s UTC. Le rattrapage a enregistré
  cette décision d'ordonnancement sans acquérir de carrière.
- Le 22 à 02 h 40 UTC, le rejeu de la décision sur le checkpoint
  `cc5e4f23` retrouve une publication globale à 01 h 45 min 11 s et son
  prochain rafraîchissement horaire à 02 h 45 min 11 s. L'écart de cinq
  minutes ne laissait pas la marge PMU de sept minutes. Le premier
  jalon de réunion s'ouvrait à 08 h 10 UTC. Le motif de pause du bilan
  de rattrapage appartenait donc à un passage précédent.

Le cycle PMU nocturne peut désormais donner le relais au workflow
incrémental après un checkpoint global confirmé. Le workflow relit les
données durables et recalcule les gardes en entrant sous le verrou partagé.
Lors d'une pause commune, la réconciliation locale et les publications
en attente peuvent progresser dans un créneau admissible. Le suivi du
rattrapage date la décision et la reprise possible indépendamment du
dernier passage d'acquisition.

[Passage du 20](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/actions/runs/44763420602)
· [Premier passage du 21](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/actions/runs/44957065733)
· [Refus 429](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/actions/runs/44957498708)
· [Contrôle du 22](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/actions/runs/44977123949)
· [Checkpoint PMU](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/commit/cc5e4f23)
