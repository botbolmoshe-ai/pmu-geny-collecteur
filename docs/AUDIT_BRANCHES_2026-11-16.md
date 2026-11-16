# Audit et nettoyage des branches — 16 novembre 2026

Dépôt : botbolmoshe-ai/pmu-geny-collecteur

## Constat vérifié

- Branches avant nettoyage : 39.
- `main` : branche par défaut et code de production.
- `pmu-data` : **conservée**. Les workflows de production utilisent cette branche pour persister les historiques, les états de collecte et les prévisions. La supprimer sans changer l'architecture ferait perdre la persistance des traitements.
- Branches ayant une pull request fusionnée dans `main` : 25; elles peuvent être retirées après contrôle du SHA.
- Branches de tests, pilotes ou WIP non fusionnés : 12. **Avant suppression, une étiquette Git (tag) portant le SHA exact est créée**, ce qui rend le contenu récupérable sans maintenir la branche.
- Aucun pull request ouvert constaté au début de l'audit.
- Les 163 identifiants Geny des historiques de `test/boucle-historiques-courus` existent tous sous `pmu-data/historiques/`.
- Toutes les suppressions sont conditionnées à l'absence de nouvelle modification du SHA de branche et de pull request ouvert.

## Résultat exécuté et vérifié

- **37 branches supprimées**, vérifiées par l'exécution GitHub Actions [43916719649](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/actions/runs/43916719649) (statut `success`).
- **12 tags d'archivage créés** avant suppression pour les travaux sans PR fusionnée.
- **2 branches restantes** lors du contrôle GitHub : `main` et `pmu-data`.
- `pmu-data` conservée volontairement pour ne pas interrompre la collecte, les checkpoints, les historiques et les prévisions.
- Aucun changement destructif des données stockées sous `pmu-data` ; aucun workflow de production modifié par le nettoyage.
- Le fichier de lancement et le workflow ponctuel de nettoyage peuvent maintenant être retirés de `main`.

## Liste de retrait

| Branche | SHA audité | Sort | Archive du travail non fusionné |
|---|---|---|---|
| `experiment/historique-equidia` | `ce31ae1d294816524fc2d2201b4e09ae1ea8b558` | Pilote / WIP abandonné | `archive/20261116/experiment-historique-equidia` |
| `experiment/historique-pmu` | `07cd118923a7746934a46190f2ad2a6b9829adc0` | Pilote / WIP abandonné | `archive/20261116/experiment-historique-pmu` |
| `experiment/historique-zeturf` | `c5d868d0edf875ff1c608f39b4c4c652b13f8a53` | Pilote / WIP abandonné | `archive/20261116/experiment-historique-zeturf` |
| `feature/collecte-historiques-independante` | `06c2a79e98fcb89a44f97206105c3c23fb904761` | Pilote / WIP abandonné | `archive/20261116/feature-collecte-historiques-independante` |
| `feature/direct-contextuel-v32-20261115` | `72a1cf0e5f481759f80df4c4a1f207338e153cab` | PR déjà fusionnée | Sans objet |
| `feature/direct-profils-sources-v32` | `7dfb7784463b2e097311323df5aba1bd450b6187` | PR déjà fusionnée | Sans objet |
| `feature/priorite-nocturne-historiques` | `759d0e91b088d48eb97d59f8a1d70e7307a9e157` | PR déjà fusionnée | Sans objet |
| `feature/rattrapage-exhaustif-geny` | `24764535f30edb704ce8ca8c484f559f703577bd` | Pilote / WIP abandonné | `archive/20261116/feature-rattrapage-exhaustif-geny` |
| `feature/reprise-historiques-globale` | `8f6da189225967307522a54c9faa395b3904c579` | PR déjà fusionnée | Sans objet |
| `feature/scoring-geny-explicable` | `df5b45f0b501ac1cc778c3deccc590616572cafe` | Pilote / WIP abandonné | `archive/20261116/feature-scoring-geny-explicable` |
| `fix/controles-synchronisation-sheets` | `c3377ebb97a508acc391447fd72ea06cc95175e7` | PR déjà fusionnée | Sans objet |
| `fix/ferrures-ambiguite-texte` | `a2897eb2fe1bd4405f5b81483f83416379a1f53c` | PR déjà fusionnée | Sans objet |
| `fix/ferrures-sources-completes` | `2d288adad6fec3795d2bb93aa0816a3dc49e3ebc` | PR déjà fusionnée | Sans objet |
| `fix/fiabilite-completude-production` | `8799538ad18d7eaf3a4d7984d6aac41a2086375b` | PR déjà fusionnée | Sans objet |
| `fix/fiabilite-musique-np-kpi` | `03b8ad11a258f147976939c2c7000d16670a5376` | PR déjà fusionnée | Sans objet |
| `fix/horodatage-bilan-rattrapage` | `d22a9e433e012792f3d78d2be58911c34c386bd2` | PR déjà fusionnée | Sans objet |
| `fix/identifiants-sources-chevaux` | `864f04476113451d87a278628cd20817b16c6b5d` | PR déjà fusionnée | Sans objet |
| `fix/j1-historiques-priorite-20261115` | `515bd63b439cc77e5907de3c9884f04af736c200` | PR déjà fusionnée | Sans objet |
| `fix/pmu-arrivals-and-course-status-20261115` | `1fe11722012e2987290005e3c3341207dec8970f` | PR déjà fusionnée | Sans objet |
| `fix/quotas-lectures-sheets` | `a473500bdadaaafab7aec9feb5c5a35e570ba2ce` | PR déjà fusionnée | Sans objet |
| `fix/reconciliation-identites-historiques` | `935f1212698402cdeb0a9435dd029d6dd5947206` | PR déjà fusionnée | Sans objet |
| `fix/reprise-carrieres-prioritaires` | `de4f3b8336623a499e1f48007ae93de0d5821c6b` | PR déjà fusionnée | Sans objet |
| `fix/reprise-contextes-registre` | `ebaf77cdc838cd500115b04569f877b5b06c7309` | PR déjà fusionnée | Sans objet |
| `fix/reprise-identifies-prioritaires` | `ffc6d34389301346bed7ba0f4777b29d0c9fee8b` | PR déjà fusionnée | Sans objet |
| `fix/revalider-captures-historiques` | `d6ab8b4aaba6e0b4579588979dc1050e12bdbfbf` | PR déjà fusionnée | Sans objet |
| `fix/sheets-dedoublonnage-complet` | `fbdb5f1e24e72cf32c38aca83d18655e02ae9774` | PR déjà fusionnée | Sans objet |
| `fix/sheets-preserver-variantes` | `8be2fee87db0168e31f9e7daab727cca3f6a681b` | PR déjà fusionnée | Sans objet |
| `fix/supprimer-colonne-avis-equidia` | `96bca62deb0b4a5ddf5388067ef7e5bc54828f4a` | PR déjà fusionnée | Sans objet |
| `fix/v32-niveau-allocation-regex` | `9d4cd65ac99620cf03fdebd5fe0e913bd58fdfdd` | PR déjà fusionnée | Sans objet |
| `integration/collecte-incrementale-production` | `a4b426dc883d1925294a886f4a2ed1fa4e6022b3` | PR déjà fusionnée | Sans objet |
| `refactor/moteur-sheets-unique` | `c457b832c19f2d094da78dc3955da285d06cd45b` | PR déjà fusionnée | Sans objet |
| `refonte-pmu-trot-20261113` | `863bb329938b5d556674b2dded32385e0410968d` | Pilote / WIP abandonné | `archive/20261116/refonte-pmu-trot-20261113` |
| `test/boucle-historiques-courus` | `c08feed67b4b3e1b86d3059ac67556521299b6fc` | Pilote / WIP abandonné | `archive/20261116/test-boucle-historiques-courus` |
| `test/historique-marvina-bella` | `433326856eae57c08ca141e628c96ee706fcbd88` | Pilote / WIP abandonné | `archive/20261116/test-historique-marvina-bella` |
| `test/priorite-cycle-complet` | `cb4e1d70a1a18cfdbf9675ad443757b315e2dda1` | Pilote / WIP abandonné | `archive/20261116/test-priorite-cycle-complet` |
| `test/rapprochement-2026-11-12` | `c45ea14a9020e10e7fa20eff0869f634bbc7ba5c` | Pilote / WIP abandonné | `archive/20261116/test-rapprochement-2026-11-12` |
| `test/simulation-collecte-couverture` | `d51fd51f3750022cd19254fe16adc490c4e9f6ed` | Pilote / WIP abandonné | `archive/20261116/test-simulation-collecte-couverture` |

## Récupération éventuelle d'une branche expérimentale

```bash
git fetch origin --tags
git switch -c ma-branche-restauree archive/20261116/nom-de-la-branche
```

Le tag préserve le dernier commit de la branche supprimée ; il ne signifie pas que le code expérimental a été intégré à `main`.

## Décision d'architecture distincte

Pour ne conserver **strictement** que `main`, il faut d'abord migrer l'ensemble des données de `pmu-data` et modifier les workflows consommateurs. Ce chantier n'est pas confondu avec le nettoyage des branches de développement.
