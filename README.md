# PMU — Collecteur historique Geny (GitHub Actions)

Prototype **sans accès en écriture à Google Sheets**, limité volontairement à **un seul cheval** et **un déclenchement manuel**. Ne pas activer la planification avant validation de l'accès depuis GitHub.

## Installation (une seule fois)

1. Créer un compte ou se connecter à https://github.com.
2. Cliquer **New repository** ; nom : `pmu-geny-collecteur` ; visibilité : **Private** ; cocher **Add a README file** ; créer le dépôt.
3. Sur la page du dépôt, choisir **Add file > Upload files**. Télécharger le contenu de cette archive sur son PC et transférer les fichiers à la racine du dépôt. Important : GitHub Web n'accepte pas de préserver les chemins de dossiers si l'on ne les transfère pas correctement ; le plus simple est de sélectionner et déposer *le dossier décompressé* dans la zone d'upload, puis de vérifier que les chemins `.github/workflows/test-geny.yml` et `pmu_geny/traitement_course.py` existent. Sinon utiliser GitHub Desktop.
4. Enregistrer via **Commit changes** sur `main`.
5. Ouvrir **Actions > Test Geny Playwright (manuel) > Run workflow > Run workflow**.
6. Lire le journal et télécharger **diagnostic-geny** (artifact ZIP) au bas de la page de l'exécution.

## Attendus du test

`resultats/bilan.json` et `resultats/2026-11-09-BORDEAUX-R1C4-TEST/2775817/historique_geny.json`. Le résultat doit indiquer le nombre annoncé et le nombre extrait, sans faire de promesse de 45/45 car le nombre affiché sur Geny évolue.

## Diagnostic

- `ERREUR_NAVIGATION`: le cloud n'accède pas à Geny ou la page a changé.
- `PARTIEL_A_CONTROLER`: nombre ou colonnes incohérents.
- `COMPLET`: extraction conforme aux contrôles de la V4 ; un contrôle indépendant des identités et de la qualité est conseillé avant écriture dans Sheets.

Les fichiers de diagnostic peuvent contenir des éléments provenant de la page web. Le dépôt privé protège le code, **mais les artifacts peuvent être visibles à toute personne ayant l'accès au dépôt**.

## Étapes suivantes, après validation cloud

- Ajouter les partants de la course dans un manifeste ou collecter les partants via une source PMU autorisée.
- Traiter un cheval à la fois, réutiliser un état/checkpoint persistant et éviter les doublons.
- Ajouter l'écriture dans Google Sheets via compte de service ou OAuth avec identifiants stockés dans les **GitHub Actions Secrets**, jamais dans le dépôt.
- Déclencher périodiquement avec un `schedule` seulement après vérification ; les événements programmés peuvent être retardés. Le figement strict TOP3 avant départ doit rester un mécanisme distinct.
- Vérifier les conditions d'utilisation du site Geny et maîtriser le rythme des requêtes.
