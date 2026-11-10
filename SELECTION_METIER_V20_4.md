# V20.4 — Périmètre trot français P1/P2

- Courses uniquement françaises (filtre PMU existant), avec **départ de 07 h 00 à 21 h 00 inclus** (Europe/Paris), **trot attelé et monté** ; un champ `TROT` sans sous-type explicite est accepté comme trot (sous-type inconnu). Toute discipline inconnue/ambiguë est exclue avec diagnostic, ainsi que plat et obstacles.
- P1 : Vincennes (trot), course Groupe I/II/III identifiée, ou allocation ≥ **40 000 €**.
- P2 : hippodrome de la liste éditoriale `HIPPODROMES_P2`, au moins **8 partants**, allocation ≥ **12 000 €** si renseignée. Allocation absente : retenue mais explicitement marquée inconnue.
- Autres courses : exclues **avant** collecte Geny, sans toucher aux anciens historiques.
- Seuils (40 k€, 12 k€, 8 partants), et liste hippodromes sont **paramètres de départ proposés**, ajustables après observation ; ils ne proviennent pas d'une règle PMU officielle.
- Le temps restant avant départ demeure la priorité de l'ordonnanceur ; dans une même fenêtre d'urgence, P1 passe avant P2.
- Audit `sources_pmu/diagnostic_DATE.json` : `courses_p1`, `courses_p2`, `decisions_metier` (motif et caractéristiques pour chaque course éligible après validations techniques). Le JSON du diagnostic ne contient aucun pari ni probabilité inventée.
- Source non reconnue : exclusion prudente, avec compteur `metier_discipline_inconnue`, à contrôler sur de vrais échantillons GitHub. Les schémas PMU de spécialité doivent être confirmés lors de la première exécution : une exécution verte avec zéro P1/P2 n'est pas un succès métier.

## Installation
Copier **le contenu** de `pmu_v20_4` à la racine du dépôt sur `main`, en conservant `.git`, puis commit/push. **Ne pas supprimer `pmu-data`.**
Démarrer le workflow `PMU - V20.4 Trot P1-P2 et orchestration` en mode `auto`, inspecter `DIAGNOSTIC_PMU` et les compteurs P1/P2 et motifs. Ne pas lancer d'autres versions en parallèle.
