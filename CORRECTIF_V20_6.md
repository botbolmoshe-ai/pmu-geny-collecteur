# PMU V20.6 — Démarrage J-1 et rapprochement PMU–Geny

## Changements

- **J-1 :** premier cycle GitHub après 18 h Europe/Paris : consultation et sélection des courses du lendemain, même pendant un cycle léger. La découverte et collecte Geny ne s'exécutent qu'en cycle complet, dans leurs quotas et sous réserve de Playwright opérationnel. Les cycles légers suivants réutilisent le programme J-1 déjà enregistré. `PLANIFICATION_J1`, `BILAN_J1`, `PLANIFICATION_J1_DEJA_EFFECTUEE` permettent de le contrôler.
- **Index Geny :** une seule visite du programme Geny par date et par période de 6 h, avec mise en cache dans `sources_geny/index_YYYY-MM-DD.json`. Respect du blocage 403/429 et du cooldown déjà en place.
- **Rapprochement :** hippodrome normalisé + nom de course comparé de façon tolérante. Refus des intitulés dissemblables et des candidats ambigus. Aucune hypothèse que RnCn PMU = RnCn Geny. Un lien confirmé conserve l'identifiant Geny dans `orchestration/correspondances_geny.json`.
- **Diagnostics :** `INDEX_GENY`, `rapprochements_ambigus`, `rapprochement_geny`, `motif_attente_geny`. Un manifeste n'est généré qu'après vérification de sa fiche et du nombre de partants ; une course sans correspondance reste connue côté PMU.
- **GitHub :** installation du paquet Python Playwright même pendant un cycle léger, mais Chromium seulement quand nécessaire.

## Installation

Sur la branche `main`, fusionner le contenu de `pmu_v20_6/` à la racine du dépôt et remplacer les fichiers. Ne pas effacer `.git` et ne pas modifier `pmu-data` ; commit puis push. Workflow unique à chemin inchangé `.github/workflows/pmu-v16.yml`.

## Vérification

À partir de 18 h, voir `PLANIFICATION_J1 date=AAAA-MM-JJ`, puis le `DIAGNOSTIC_PMU` du lendemain. Sur cycle complet : `INDEX_GENY date=... statut=OK courses=N` et les compteurs de manifestes. Le résultat **n'est pas une garantie** de couverture complète : Geny peut refuser l'accès ou ne pas exposer de liens exploitables. Aucun faux rapprochement n'est forcé.

## Tests

`python -m unittest discover -s tests -q`

Le modèle ML reste conditionné aux jeux d'entraînement réels et aux arrivées officielles ; aucune cote n'entre dans ses caractéristiques.
