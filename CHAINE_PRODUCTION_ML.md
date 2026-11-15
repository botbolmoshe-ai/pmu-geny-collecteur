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
précédentes sont archivées. Le schéma `pmu-podium-v33` évite de réutiliser un ancien
modèle entraîné avec un parcours de variables différent.

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

L'apprentissage de production et l'expérience manuelle réutilisent le même
validateur `experience_ml.run()`. Seules les captures antérieures au départ et
les arrivées horodatées après départ, déjà observées, sont admissibles. Le podium
complet doit appartenir aux chevaux capturés ; les NP inconnus et formats invalides
sont écartés.

Les seuils d'entrée restent **100 courses et 700 lignes cheval**. Les deux derniers
jours admissibles servent respectivement à la validation et au test ; les jours
précédents servent à l'apprentissage initial. Les candidats sont choisis sur la
validation, puis réentraînés sur apprentissage+validation. Le jour test reste exclu
du modèle sauvegardé. La disponibilité temporelle des étiquettes est contrôlée.

La promotion exige un comparateur « forme PMU » complet au même instant de capture
sur toutes les courses test et un écart positif dont la borne basse du bootstrap
par course est strictement supérieure à zéro. Sinon le candidat reste dans
`ml/experiences/` et l'éventuel modèle précédent est conservé. Cette règle est un
filtre opérationnel conservateur ; elle ne démontre pas une fiabilité durable ni
une calibration des probabilités. Les scores restent explicitement non calibrés.

La finalité définitive des arrivées anciennes n'étant pas tracée par le collecteur,
cette limite reste indiquée dans les rapports ; aucune garantie de réussite n'est
associée à une promotion.

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
