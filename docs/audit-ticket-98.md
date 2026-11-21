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
