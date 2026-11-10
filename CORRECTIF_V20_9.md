# V20.9 — rapprochement PMU / Geny (11/11/2026)

## Ce que corrige cette livraison

1. Le code R/C de l’éditeur Geny n’est plus considéré comme une preuve négative décisive, car la numérotation peut être différente de celle du PMU.
2. Confirmation possible si **date, hippodrome normalisé et intitulé de course fortement identique** concordent, et si la course Geny est unique dans le contexte de la réunion.
3. Toute divergence R/C confirmée est tracée dans `preuves.code_rc_different`, `preuves.pmu_rc` et `preuves.geny_rc` ; méthode `NOM_FORT_RC_DIFFERENT`.
4. Maintien du refus des homonymes, noms insuffisamment proches, dates et hippodromes différents. Un repli flou reste limité aux candidats sans R/C documenté, avec score/marge de sécurité.
5. Chaque tentative de rapprochement produit une ligne JSON `RAPPROCHEMENT_GENY` exploitable dans le journal GitHub Actions.
6. Toutes les autres fonctions de V20.8 sont conservées, notamment le secret Google Sheets, le stockage persistant `pmu-data`, les trois onglets, le cooldown Geny 403/429, et les prévisions déjà existantes.

## Installation

Décompresser cette archive et copier **le contenu intérieur du dossier `pmu_v20_9`** à la racine de `main` du dépôt GitHub, en remplaçant les fichiers de V20.8. Ne pas toucher à `.git`, à `pmu-data`, au secret `GOOGLE_SHEETS_SERVICE_ACCOUNT_JSON` ou aux données existantes. Commit, puis Push.

Dans GitHub Actions, choisir «PMU - V20.9 Rapprochement PMU Geny et tableau de bord», cliquer `Run workflow` avec `mode = auto`. Vérifier les lignes `INDEX_GENY`, `RAPPROCHEMENT_GENY`, `BILAN_J1`, `SYNC_GOOGLE_SHEETS`.

**Limites importantes** : les tests sont des tests Python hors réseau et non une preuve de collecte réelle réussie. Geny peut répondre 403/429; dans ce cas la suspension reste volontaire, les rapprochements indisponibles restent non vérifiés. Si l’index Geny ne peut pas être obtenu, le moteur ne peut pas associer des courses nouvelles. Cette version ne prouve ni la production d’un TOP3 dégradé sans manifeste ni la disponibilité des arrivées officielles: ces points doivent être constatés en production.
