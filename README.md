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

## Test multi-chevaux — Bordeaux R1C4, 9 novembre 2026

Le workflow **PMU - Test course complète (manuel)** (`.github/workflows/test-course.yml`) réalise deux étapes :

1. Ouvre le programme officiel Geny de la journée et cherche la fiche du **Prix Caliceo** ; récupère exclusivement les liens des chevaux correspondant à l'identifiant de cette course. Il exige **14 fiches distinctes** avant de poursuivre. Si la détection n'est pas certaine, il s'arrête et fournit les diagnostics ; **aucune association n'est inventée**.
2. Collecte séquentiellement les historiques avec le moteur V4. Un rapport `resultats/bilan.json` est produit. Le ZIP **bilan-course-geny** est disponible dans Artifacts, y compris en cas de problème si des diagnostics ont été créés.

### Mode opératoire

- Copier **les deux fichiers nouveaux** `.github/workflows/test-course.yml` et `pmu_geny/decouverte_partants.py` dans le dépôt local via GitHub Desktop, puis **remplacer** `pmu_geny/traitement_course.py` par cette version (les autres fichiers restent inchangés).
- Dans GitHub Desktop : `Commit to main` puis `Push origin`.
- Sur GitHub > Actions > `PMU - Test course complète (manuel)` > `Run workflow`.
- Laisser `course_url` vide (découverte depuis le programme Geny). Choisir `max_chevaux=3` pour le premier contrôle ; puis `14` après validation.
- Si la découverte automatique échoue, ouvrir le ZIP `bilan-course-geny`, inspecter `decouverte/fiche_course.png` et `decouverte/liens_fiche_course.json`. On peut passer l'URL **réelle** de course Geny dans `course_url` lors du relancement. Ne pas fournir d'URL supposée.

**Limites :** disponibilité et HTML Geny non vérifiés pour ce nouvel extracteur de partants, distinct du collecteur d'historiques déjà testé. Ce workflow ne planifie rien, ne calcule pas de TOP3 et n'écrit pas dans Google Sheets. La sélection complète des partants doit être validée avant une utilisation quotidienne.
