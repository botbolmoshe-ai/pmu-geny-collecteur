# Reprise PMU dans cet environnement

État vérifié le 12 novembre 2026, vers 20 h 15 UTC (21 h 15 à Paris).

## Projet repris

- Dépôt privé : https://github.com/botbolmoshe-ai/pmu-geny-collecteur
- Code cloné avec son historique et ses branches dans `/workspace/PMU`.
- Branche de travail actuelle : `main`, commit `2c854d56c515cc7d1c1e091e70522e55806d323e`.
- Copie locale des données : `reference_pmu/`, extraite de `origin/pmu-data`, commit `05556ec3a8a37e7be6d94b72944ff5ec6b4cd7af` (12 novembre, 19 h 46 UTC).
- Environnement Python 3.12 isolé : `.venv/`, dépendances de `requirements.txt`, scikit-learn 1.7.2 et joblib 1.5.2 installés.

`reference_pmu/` est un instantané pour l'analyse, sans synchronisation automatique. Il est exclu des commits par `.git/info/exclude`, comme `cache_pmu/`. Les commandes de vérification ci-dessous lisent cet instantané et écrivent seulement leurs rapports locaux dans `resultats/`.

## Vérifications réalisées

- Régression hors ligne : **104 tests, tous réussis** ; journal `resultats/reprise/tests.log`.
- Audit des historiques : **23 manifestes, 49 historiques, 46 complets et 3 partiels**, aucune erreur de lecture/cohérence des manifestes détectée. Rapport : `resultats/reprise/audit/rapport.json`. Cela ne démontre pas la qualité prédictive.
- Registre depuis le 12 novembre : **23 courses, 318 lignes de partants, 13 lignes de bilan et 1 023 performances historiques** dans les tables produites par le module existant. Il couvre aussi des courses préparées pour le lendemain. Rapport : `resultats/reprise/qualite.json`.
- Le contrôle du registre voit des TOP3 directs pour les 23 courses, mais aucun TOP3 historique ou ML complet dans ses lignes. Le journal d'orchestration du 12 novembre signale pourtant une sélection déjà figée : la cohérence entre fichiers de prévision, exports et registre reste à examiner.
- Extraction du jeu ML actuel, sans entraînement : **18 courses et 254 lignes admissibles**, sous les seuils existants de 100 courses et 700 lignes. Aucun fichier `modele.joblib` présent dans l'instantané. Le fichier de statut d'entraînement date du 10 novembre ; il ne décrit pas la taille actuelle du jeu.
- Trois dernières exécutions GitHub Actions consultées : terminées avec succès (12 novembre, lancements 17 h 42, 18 h 40 et 19 h 44 UTC). Ce statut ne garantit pas la complétude fonctionnelle du cycle.

## Commandes locales

Depuis `/workspace/PMU` :

```bash
.venv/bin/python -m unittest discover -s tests -p 'test_*offline.py' -q
.venv/bin/python -m pmu_geny.audit_generique_hors_ligne --source reference_pmu --sortie resultats/reprise/audit
.venv/bin/python -m pmu_geny.qualite_registre_v21 --cache reference_pmu --debut 2026-11-12 --sortie resultats/reprise/qualite.json
```

Pour reconstruire cet environnement Python :

```bash
python -m venv .venv
.venv/bin/python -m pip install -r requirements.txt scikit-learn==1.7.2 joblib==1.5.2
```

L'accès réseau du terminal a nécessité l'exécution approuvée hors du sandbox de commande : le proxy n'était pas joignable depuis ce sandbox. Le connecteur GitHub fonctionne aussi pour lire le dépôt.

## Périmètre de cette reprise

Le code et les données sauvegardées sont disponibles pour développer, tester et diagnostiquer le projet ici. Cette reprise n'a déclenché aucune collecte hippique, modification de Google Sheets, écriture distante, ni nouvelle automatisation. Le processus planifié existant reste sur GitHub Actions.

Avant une collecte locale, installer le navigateur Chromium correspondant à Playwright si nécessaire, puis vérifier l'accès réel aux sources. Les tests hors ligne n'établissent pas cet accès.

La synchronisation Google Sheets utilise `GOOGLE_SHEETS_SERVICE_ACCOUNT_JSON` et `GOOGLE_SHEETS_ID` dans le code. Les secrets de GitHub Actions ne sont pas automatiquement disponibles dans ce terminal. Toute configuration nécessaire se fait dans les réglages sécurisés de l'environnement.

## Prochaines priorités techniques

1. Examiner les trois historiques partiels et la cohérence entre TOP3 persistés, exports et registre.
2. Vérifier la chaîne de bout en bout sur une course : données pré-départ, sélection figée, arrivée officielle et bilan comparable.
3. Accumuler des courses admissibles, puis valider le modèle chronologiquement et contrôler sa calibration avant d'annoncer des probabilités.

Les règles de `REGLES_AUDIT_PREDICTIF.md` s'appliquent : cotes exclues des variables de prédiction, absence de données postérieures au départ dans les instantanés, conservation des sélections initiales et des historiques.
