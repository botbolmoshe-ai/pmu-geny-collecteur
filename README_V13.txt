V13 - Diagnostic du rang 12e / 6e d'Ocean Dairpet

Copier dans le depot GitHub :
  pmu_geny/collecte_geny_v4.py  (remplace V12)
  pmu_geny/test_parser_v13.py (nouveau)
  .github/workflows/test-ocean-v13.yml (nouveau)

Ne pas remplacer les autres fichiers du depot.
Commit to main > Push origin.
Actions > PMU - V13 Diagnostic Ocean Dairpet (manuel) > Run workflow.

La commande du workflow teste uniquement Ocean Dairpet, sans relancer les 14.
Telecharger l'artefact diagnostic-ocean-v13 et verifier historique_geny.json.

IMPORTANT: V13 ne corrige pas le cache historique marque PARTIEL par les runs passes.
Ne pas relancer les 14 avant verification du test cible. Le diagnostic cible
ne lit pas le cache, et permet de valider les rangs reels de ce cheval.
Le test hors ligne utilise les rangs et la structure de l'exemple fourni, pas
un dump DOM reel d'Ocean Dairpet.
