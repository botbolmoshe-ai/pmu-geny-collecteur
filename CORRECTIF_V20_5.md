# V20.5 – Correctifs ciblés

- Normalisation des noms PMU : `HIPPODROME DE PARIS-VINCENNES` → `vincennes` (P1 sans condition d’allocation).
- Reims et autres hippodromes P2 : suppression des préfixes de présentation ; les seuils P2 demeurent inchangés.
- Traces `PLANIFICATION_J1` et `BILAN_J1` lors des cycles complets à partir de 18 h, heure de Paris.
- Les courses passées ne sont pas reprises en collecte Geny ou pronostics ; la branche `pmu-data` est conservée.
- **Limite** : un cycle léger de 18 h 45 n’affiche que la journée courante ; rechercher l’exécution complète suivante pour observer le lendemain.
- **Limite** : l'association PMU–Geny reste basée principalement sur un rapprochement de noms ; aucune garantie de couverture complète n'est apportée par cette version.
- Les nouveaux diagnostics `DIAGNOSTIC_PMU` sont visibles dans les logs et enregistrés sur `pmu-data`.

Installation : copier le contenu de `pmu_v20_5` à la racine du dépôt sur `main` en conservant `.git`, puis commit et push. Lancer `auto`.
