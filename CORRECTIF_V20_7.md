# V20.7 — Correspondance R/C sous contrôle

- Clé prioritaire : date + hippodrome normalisé + R/C, lorsque Geny expose les deux numéros dans un bloc DOM local non ambigu.
- Si le code R/C est absent : conservation du rapprochement V20.6 par hippodrome et intitulé.
- Si les codes observés se contredisent ou si le titre est incompatible : rejet avec diagnostic, sans associer arbitrairement les chevaux.
- Les numérotations entre PMU et Geny ne sont **pas garanties identiques**. Le rapprochement direct reste conditionné à l'observation des deux codes.
- Les pages Geny n'ont pas encore été validées en exécution GitHub pour l'extraction R/C ; ne pas interpréter l'absence de codes comme une erreur fatale.
- Tous les filtres métier trot P1/P2, règles de non-partants, entraînement ML, cotes de contrôle et cooldown sont préservés.

## Installation
Décompresser, copier le contenu de `pmu_v20_7/` à la racine du dépôt sur `main` sans supprimer `.git` ni modifier `pmu-data`, commit, push. Lancer `auto`.
