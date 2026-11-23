Chaîne de production et apprentissage ML : voir
[`CHAINE_PRODUCTION_ML.md`](CHAINE_PRODUCTION_ML.md) pour le raccordement PMU,
le cycle quotidien unique, l'expérience manuelle et les conditions de promotion.
Cette description remplace les modalités ML historiques V19/V20 ci-dessous.

Processus actuel de collecte des historiques : voir
[`COLLECTE_INCREMENTALE_PRODUCTION.md`](COLLECTE_INCREMENTALE_PRODUCTION.md).
Sources de données actuellement branchées et gestion de leurs identifiants :
[`SOURCES_DONNEES_ACTUELLES.md`](SOURCES_DONNEES_ACTUELLES.md).
PMU fournit les critères courants, Geny les historiques. Equidia et ZEturf sont
retirés des appels automatiques ; Open-Meteo reste le complément météo sourcé.
Collecte et reprise des ferrures :
[`FERRURES_COLLECTE.md`](FERRURES_COLLECTE.md).
Synchronisation commune aux déclencheurs :
[`MOTEUR_SHEETS_UNIQUE.md`](MOTEUR_SHEETS_UNIQUE.md).

Reprise du stock d'historiques, toutes dates confondues :
[`RATTRAPAGE_HISTORIQUES.md`](RATTRAPAGE_HISTORIQUES.md).
Il remplace la collecte par lots décrite dans les anciennes versions ci-dessous.

Voir `CORRECTIF_V20_6.md` pour les changements de l’ordonnanceur J-1 et du rapprochement PMU–Geny.

# PMU V20 — météo sourcée (évolution incrémentale V19)

## Ajout vérifié en tests locaux

- `pmu_geny/contexte_meteo_v20.py` : une prévision horaire Open-Meteo par hippodrome français **lorsque le géocodage exact et non ambigu de la ville est possible**. La météo est géolocalisée à la ville, pas à la piste. Les hippodromes dont le nom diffère de la ville (ex. Le Croisé-Laroche) restent `METEO_NON_VERIFIEE` sans table de coordonnées validées.
- Réactualisation au maximum toutes les 45 minutes, uniquement **avant** le départ ; date et URL source enregistrées. Les valeurs manquantes ne sont pas remplies par des estimations.
- Température (°C), humidité (%), vent (km/h), précipitation horaire (mm) sont ajoutés aux instantanés historiques et aux variables ML, et aux colonnes du CSV comparatif.
- Les **cotes ne sont jamais des variables du modèle**. Les conditions réelles observées après le départ ne sont jamais réinjectées dans l'apprentissage. Les prévisions météo d'autrefois ne sont pas reconstituées avec des observations réelles a posteriori.
- **État de piste, ferrure, commentaires, bruits d'écurie :** leur présence sur les sites PMU, Geny et ZEturf a été vérifiée sur les pages publiques, mais aucun extracteur automatisé fiable et autorisé n'est intégré ici. Les champs `avis_experts_score`, `info_ecurie_score` restent manquants sans observation préalable sourcée. Ne pas les annoncer comme collectés.
- **Modèle existant :** l'ajout de deux variables implique un réentraînement ; le modèle V19 reste conservé mais sera signalé `MODELE_SCHEMA_OBSOLETE_REENTRAINEMENT_REQUIS` jusqu'au réentraînement. Pas de suppression des données `pmu-data`.
- **Accès :** API Open-Meteo gratuite sans clé pour un usage non commercial, limites et attribution selon les conditions officielles. Une exécution sur GitHub Actions reste à confirmer.

## Installation

Copier le contenu de ce dossier à la racine du dépôt GitHub, commit et push. Ne rien supprimer dans `pmu-data`. Garder le workflow `.github/workflows/pmu-v16.yml` (chemin historique conservé) : l'intitulé affiché passe en V20.

## Tests

```bash
python -m unittest discover -s tests -p 'test*offline.py' -q
python -m unittest discover -s tests -p 'test_v20_meteo_offline.py' -q
```

## Provenance des variables

`cache_pmu/contextes/YYYY-MM-DD_RnCn.json` conserve la capture météo antérieure au départ. `cache_pmu/exports/GENY-ID/comparatif_predictions.csv` affiche côte à côte ses indicateurs météo, les TOP3 baseline/ML, les cotes informatives et l'arrivée.

---

# PMU V19 — Comparatif TOP3 baseline / Machine Learning

## Installation
Copier **le contenu** de ce dossier dans la racine du dépôt GitHub existant (`main`), commit puis push via GitHub Desktop. Ne rien effacer sur la branche `pmu-data`. Le workflow `.github/workflows/pmu-v16.yml` est **modifié sur place** et affiché comme **PMU - V19 Orchestration et ML** : aucun workflow concurrent à créer.

## Ce qui est opérationnel dans le code
- Ancien collecteur Geny et stockage V16–V18 préservés.
- Pour les réunions de trot P1/P2, les jalons Direct et ML H-3 puis H-2 sont calculés depuis le premier départ de la réunion. La ponctualité est attestée par la relecture de Sheets. Les anciens certificats et relevés KPI conservent leur heure et leur libellé.
- Baseline expérimentale de référence à H-2 (fenêtre de capture H-2h15 à H-2h00); à la déclaration ultérieure d'un NP : nouvelle baseline sans le cheval retiré, **la référence initiale n'est pas réécrite**.
- Génération automatique de `exports/GENY-ID/comparatif_predictions.csv` : un enregistrement par cheval, classements baseline initial/final, classement ML si entraîné, cotes horodatées, résultats et nombres de bonnes sélections, statut NP.
- Instantanés de **variables pré-départ uniquement**, sans cotes, cotes séparées sous `cotes/`, audit des horodatages.
- Modèles scikit-learn (régression logistique, histogram gradient boosting) entraînés sur des courses distinctes ordonnées chronologiquement ; sélection à partir de la validation temporelle et réentraînement journalier à 20 h (heure France), si données disponibles.
- Un modèle absent ou sous-entraîné donne **ML_NON_ENTRAINE**, jamais une probabilité inventée.

## Conditions impératives pour un véritable apprentissage
Le jeu d'entraînement ne peut être constitué qu'après enregistrement d'**instantanés avant départ ET d'arrivées officielles après course**. Conditions minimales par défaut : 100 courses complètes et 700 lignes individuelles. Ce sont des seuils de *début d'entraînement*, pas des preuves de fiabilité. Les performances doivent être évaluées sur un historique temporel indépendant; la calibration des probabilités et l'optimisation du TOP3 sont des étapes ultérieures.

## Limites actuelles, ne pas confondre avec fonctions opérationnelles
- Cotes : relevé de la cote à la dernière vérification PMU **avant** le départ (si le champ JSON peut être interprété). Ce n'est **pas nécessairement** la cote définitive exacte « au départ ». Pas de valeur imputée si indisponible.
- Météo, état de piste, driver, entraîneur, rapports des écuries, avis des experts : **champs prévus dans les caractéristiques ML**, mais **aucun collecteur automatique de ces sources n'est encore opérationnel**. Des observations sourcées peuvent être intégrées par fichier JSON ; sans observation vérifiée, le champ reste `None`.
- La découverte automatique de toutes les courses PMU et l'accès aux arrivées / non-partants reposent sur une API PMU non documentée : non encore validés en exécution réelle GitHub. Geny peut refuser l'accès.
- En cas de départ d'une course pendant le retard d'un cron GitHub, un jalon pré-départ peut être manqué. Ne jamais reconstruire a posteriori les features.
- Le baseline ne modélise pas encore les effets tactiques suite aux NP ; il élimine les NP et reclasse les partants selon leurs scores de forme. La prédiction ML recalcule les features avec NP mais doit bénéficier de données de contexte pour apprendre l'effet tactique.
- Le cron V19 conserve quatre déclenchements par heure. Sur GitHub privé, les minutes facturables peuvent être supérieures au quota gratuit : surveiller l'onglet **Billing** et réduire la fréquence si nécessaire.

## Exemple d'observation sourcée facultative
Créer sur `pmu-data` un fichier `contextes/2026-11-15_R2C1.json` :

```json
{
  "observations": [
    {"numero": 4, "champ": "info_ecurie_score", "valeur": 0.4,
     "source_url": "https://exemple.fr/source-reelle", "collecte_utc": "2026-11-15T12:00:00+00:00"},
    {"champ": "meteo_pluie_mm", "valeur": 1.2,
     "source_url": "https://exemple.fr/meteo-reelle", "collecte_utc": "2026-11-15T12:00:00+00:00"}
  ]
}
```
Ce sont des **valeurs fictives d'illustration**, pas des données réelles. Ne pas utiliser ce fichier comme source en production. Les scores d'expertise nécessitent une grille de codage documentée avant usage.

## Validation locale hors ligne

```sh
python -m unittest discover -s tests -p 'test_*.py' -v
```

## Organisation du stockage
`ml/instantanes/DATE_RxCy.json` : features figées avant départ ; `ml/entrainement.json` : statut et validation ; `ml/modele.joblib` : modèle seulement si seuil atteint ; `pronostics/DATE_RxCy_top3.json` : baseline de référence H-2 (H-1 dans les archives) ; `pronostics/DATE_RxCy_baseline_latest.json` : ajustement après NP ; `pronostics/DATE_RxCy_ml_latest.json` : dernière prédiction ML ; `cotes/DATE_RxCy.json` : horodatage et historique des relevés; `arrivees/` : résultats vérifiés ; `exports/GENY-ID/comparatif_predictions.csv` : tableau comparatif.

## Important pour interpréter un CSV
Les cotes restent **purement informatives et totalement exclues** des variables du modèle (vérifié par test). Une cellule ML vide signifie : **pas de modèle entraîné ou pas de prédiction vérifiable**, pas un pronostic égal à zéro. Les absences de sources météo / écuries ne sont jamais remplacées par des appréciations inventées.

## V20.1 — Audit prédictif et apprentissage des erreurs

Doctrine pérenne : voir `REGLES_AUDIT_PREDICTIF.md`.
Après arrivée officielle enregistrée, le cycle `auto` génère `audits/AAAA-MM-JJ_RxCy.json` et actualise `audits/bilan_comparatif.csv` avec les scores baseline H-2, baseline après NP, ML, et marché indicatif (rang des cotes). Les cotes ne sont **jamais** utilisées par le ML. L'audit ne modifie pas automatiquement le modèle ; ses constats doivent être validés sur plusieurs courses et hors échantillon avant toute modification des pondérations. Les données et conclusions restent explicitement absentes lorsqu'elles sont invérifiables.


## V20.2 — Ordonnancement J-1 / Jour J

- **J-1 après 18 h Europe/Paris** : identification et association des courses du lendemain; pas de prédiction définitive et pas de consultation massive PMU.
- **Jour J, 7 h–21 h 59** : cycle horaire de préparation et cycles de contrôle rapprochés toutes les 15 minutes. Les horaires sont filtrés en heure locale Europe/Paris pour la gestion été/hiver.
- **Priorités** : départs dans les 2 h, puis 2–6 h, puis autres courses du jour, puis J-1, et seulement ensuite collecte des arrivées récentes; le tout dans un nombre limité de courses par cycle.
- **Après l'heure prévue du départ** : aucune nouvelle prévision, collecte Geny ou météo. Seules l'arrivée officielle, la consolidation et l'audit peuvent être traités dans une fenêtre de 4 h. Une course archivée sort du cycle.
- **Non-partants** : contrôle PMU dans les 6 h du départ (lors des rafraîchissements pré-départ); chaque nouveau retrait confirmé est pris en compte dans la prévision actualisée. Pas de NP inventé en cas d'indisponibilité.
- **Cotes** : conservées à titre informatif, jamais comme variables ML.
- **Limites** : l'association de courses PMU/Geny et la disponibilité du flux PMU nécessitent toujours une validation en conditions réelles. Le nombre de nouvelles fiches Geny reste plafonné à trois par cycle complet, le quota de demain ne force aucune consultation supplémentaire dans l'implémentation actuelle. Les déclenchements GitHub Actions peuvent être retardés.

## Correctif V20.5

Voir `CORRECTIF_V20_5.md` pour la reconnaissance des hippodromes et le diagnostic J-1.

## V20.7 : association par R/C
Voir `CORRECTIF_V20_7.md`.


## Correctif V20.9
Voir `CORRECTIF_V20_9.md` : rapprochement PMU–Geny sécurisé en cas de R/C renuméroté, journaux `RAPPROCHEMENT_GENY`.
