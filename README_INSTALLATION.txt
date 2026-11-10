PMU GENY V11 — TEST MANUEL D'UNE COURSE DE 14 CHEVAUX
======================================================

INSTALLATION
1. Decompresser ce ZIP.
2. Copier TOUS les fichiers et dossiers contenus dans le dossier pmu_v11_complet
   a la RACINE du depot GitHub pmu-geny-collecteur (PAS le dossier parent).
3. Remplacer les fichiers portant les memes noms ; conserver les autres workflows.
4. GitHub Desktop : Commit to main, puis Push origin.
5. GitHub.com > depot > Actions > 'PMU - V11 Course 14 chevaux (manuel)'
   > Run workflow > branche main > max_chevaux = 14 > Run workflow.
   Laisser course_url vide pour la course PILOTE du 10 novembre 2026.
6. Telecharger l'artefact 'bilan-pmu-v11-14-chevaux', lire resultats/bilan.json.

COMPORTEMENT
- Identification de 14 partants, puis collecte sequentielle au maximum 14 chevaux.
- Controle des donnees et statuts detailles.
- Un 429 suspend SEULEMENT les requetes Geny restantes : la course reste A_POURSUIVRE.
- Les historiques complets sont conserves dans le cache GitHub Actions avec leur JSON/CSV.
- Le cache Github peut etre evince et n'est PAS une base de donnees permanente.
- Ne calcule pas encore de TOP3 ; le mode DEGRADE/COMPLET est une recommandation.
- N'ecrit pas dans Google Sheets.
- Les courses futures demanderont un paramétrage et une decouverte adaptes.
- Attention: le site peut limiter le debit (429). Ne pas relancer en boucle.

VALIDATION
- Compilation syntaxique et scenarios simules executes localement.
- Pas encore de preuve d'extraction reussie de 14/14 sur Github.

V12 : correctif QUALIFICATION
- Une qualification n'est pas une course et ne doit pas etre comptabilisee dans le nombre de performances Geny.
- Le parseur exclut les lignes de qualification seules ou concatenees a une course,
  sans effacer la performance precedente quand deux dates sont detectees.
- Nouveau diagnostic : blocs_qualification_exclus.
- Remplacer uniquement pmu_geny/collecte_geny_v4.py dans le depot existant,
  puis Commit to main, Push origin et relancer PMU - V11 Course 14 chevaux (manuel).
- Aucune requete supplementaire vers Geny pour cette correction.
