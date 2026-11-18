# Chaîne de production et apprentissage ML

Le workflow existant `.github/workflows/pmu-v16.yml` reste le seul orchestrateur
global. Les collecteurs d'historiques gardent leur groupe de concurrence commun
`pmu-donnees-production` pour sérialiser les écritures sur `pmu-data`.

## Ordre du cycle automatique

1. Restaurer `pmu-data` et réparer uniquement les ferrures reconnues comme erronées.
2. Traiter J : partants PMU, contexte, TOP3 direct/cotes et capture/inférence ML.
   La décision est limitée à J, 07 h–21 h Paris, strictement avant départ.
   L'historique Geny enrichit les données ; son absence ne bloque pas le chemin PMU.
3. Récupérer les arrivées manquantes de J-1, sans prévision rétrospective.
4. Préparer J+1 ; les historiques du lendemain sont prioritaires pendant la nuit.
5. Appeler **une fois** `pmu_geny.cycle_ml`, après les trois cycles.
6. Contrôler la qualité, archiver les diagnostics, persister `pmu-data`, puis
   synchroniser le registre avec le moteur Sheets existant.

La collecte d'historiques reste indépendante et respecte refus, délais et reprise.
Les expériences ML n'ajoutent aucun appel à PMU ou Geny.

## Capture et prédiction

`ml_v19.pmu_rows()` est l'extracteur partagé : identité exacte, historique relié,
forme PMU, âge, sexe, gains et ferrure, plus contexte sourcé disponible.
Les cotes, résultats et rapports sont exclus des variables du modèle.

Une capture existante n'est jamais réécrite ou enrichie après coup. Le défaut de
nom écrasé par le code de ferrure « PP » est corrigé pour les nouvelles captures.
La prédiction courante filtre les NP et refuse un statut NP inconnu ; ses versions
précédentes sont archivées. Le schéma `pmu-podium-v34` documente les nouveaux critères. Le schéma v33 reste
lisible pour un modèle historique déjà en service.

## Déclenchement quotidien

Le cycle ML est autorisé après 20 h Europe/Paris, sans fenêtre de quinze minutes.
`ml/cycle.json` conserve le jour et l'empreinte des captures/arrivées. Un cycle déjà
traité avec les mêmes données ne relance pas l'apprentissage. Des données nouvelles
autorisent une nouvelle tentative ; une interruption technique reste reprenable.
Le statut réel est écrit dans `ml/entrainement.json`, même sous les seuils.

```sh
python -m pmu_geny.cycle_ml --cache cache_pmu
```

Le mode manuel `entrainer_ml` du workflow force seulement la planification :
**les seuils et les contrôles de validation restent appliqués**.

## Validation et promotion

L'apprentissage utilise des captures antérieures au départ et des arrivées déjà
observées après le départ. Les historiques Geny enrichissent la ligne du partant
si la fiche est sourcée, reliée par identité, collectée avant le relevé et si
les performances datent d'un jour antérieur à la course. Les performances
historiques ne créent pas de nouvelles lignes supervisées.

La validation chronologique choisit entre régression logistique et gradient
boosting. Elle rapporte l'effet du retrait de chaque critère sur la validation.
Le jour test reste exclu du modèle candidat, et chaque étiquette d'apprentissage
doit être observée avant la première capture de la période qui l'évalue.
Les captures anciennes contribuent avec leurs seuls champs repris par le schéma
courant. Les seuils comptent les captures du schéma courant, appariées à une
arrivée PMU sourcée. La complétude exige, pour chaque ligne, forme PMU, distance,
discipline, âge, sexe et gains. La couverture de la ferrure, de l'historique
comparable, du driver et de l'entraîneur est publiée séparément. Les deux
derniers critères utilisent les identités explicites du PMU. Leur taux de
podium est lissé à partir des captures qualifiantes des 90 derniers jours,
dans la même discipline, avec au moins cinq participations sur deux courses.
Seules les arrivées déjà observées à l'instant du relevé entrent dans ce taux.

| Niveau | Courses qualifiantes | Observations qualifiantes | Courses prospectives | Complétude |
| --- | ---: | ---: | ---: | ---: |
| Préproduction | 150 | 1 500 | 30 | 80 % |
| Production validée | 300 | 3 000 | 100 | 90 % |

Les seuils sont configurables avec les variables GitHub Actions
`ML_PREPRODUCTION_*` et `ML_PRODUCTION_*` et les suffixes `COURSES`,
`OBSERVATIONS`, `PROSPECTIVES` et `COMPLETUDE`. Pour la complétude, utiliser
une valeur décimale entre 0 et 1. Une cohorte conserve ses seuils de lancement.

Après les seuils d'apprentissage de préproduction, le modèle candidat est
figé et évalué en parallèle du modèle en service. Chaque paire utilise le même
relevé PMU que le TOP3 direct. Elle compte une fois par course, après confirmation
de la publication du TOP3 direct avant départ puis vérification de l'arrivée.
Le contrôle de promotion a lieu sur la première cohorte atteignant l'effectif
prospectif fixé. Il exige une borne basse strictement positive pour l'intervalle
bootstrap apparié à 95 %, exprimé en chevaux retrouvés par course. Un rejet
laisse le modèle en service et le TOP3 direct disponibles. Le candidat n'est
pas réentraîné entre son évaluation et sa promotion.

Le cycle inscrit les effectifs, couvertures et résultats sous
`ml/maturite.json`. Une décision favorable ajoute `ml/preuve_promotion.json`
avec les empreintes de la version et les preuves appariées. Les indicateurs
sont relus dans « Data Quality & KPI » après synchronisation et visibles dans
la section « Maturité ML » du registre actuel de Streamlit. Les scores restent
non calibrés. Le collecteur ne trace pas la finalité définitive de l'arrivée.

## Expérience sans promotion

Dans le workflow, choisir `experience_ml` et renseigner `ml_validation` et `ml_test`
au format AAAA-MM-JJ. Le résultat est persisté sous
`ml/experiences/manuel-<run_id>/`, avec modèle expérimental, rapport, scores et
empreintes SHA-256. Cette action ne modifie pas `ml/modele.joblib`.

En local :

```sh
python -m pip install -r requirements-ml.txt
python -m pmu_geny.experience_ml --cache reference_pmu \
  --sortie resultats/experience --validation 2026-11-14 --test 2026-11-15
```

Les dates ci-dessus rejouent une expérience historique. Réutiliser cette journée
pour régler les paramètres empêcherait d'en faire un nouveau test indépendant.

## Entretien et contrôles

- Les versions ML sont centralisées dans `requirements-ml.txt`, partagé par CI et production.
- La CI couvre `pmu_geny/**`, `tests/**`, `scripts/**`, les dépendances et workflows.
  La liste manuelle de fichiers qui risquait d'oublier les nouveaux modules est retirée.
- Le second appel de prédiction ML dépendant de Geny et le triple déclenchement
  potentiel de l'entraînement dans `auto_v18` sont retirés.
- Les anciennes captures, données, modèles expérimentaux et branches de travail
  non fusionnées ne sont pas supprimés par cette intégration.

```sh
python -m compileall -q pmu_geny scripts tests
python -m unittest discover -s tests -p 'test_*.py' -q
```
