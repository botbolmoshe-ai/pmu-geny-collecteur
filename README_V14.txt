PMU Geny V14 — correction de reconnaissance d’une page 403 (même si HTTP 200)

Installation : copier le CONTENU du dossier pmu_v11_complet dans la racine du dépôt GitHub ; conserver .github caché. Commit to main, Push origin.

Test local sans réseau : python -m pmu_geny.test_diagnostic_v14
Test GitHub : relancer le workflow V11 MANUEL uniquement après que Geny soit accessible. Ne pas multiplier les requêtes en cas de 403/429.

Modification : reconnaissance 403 dans le HTML dataLayer error_status, le titre et le texte, en priorité sur CARRIERE_NON_DETECTEE. Arrêt immédiat du collecteur sur 403/429 ; propagation du statut dans l’orchestrateur ; suspension de la collecte Geny pour la durée de l’exécution. Les autres étapes de traitement ne sont pas interrompues. Aucun contournement ni retry automatique.

Remarque : V13 rangs 12e et 6e conservés. Qualité extraction Geny réelle à confirmer ultérieurement. GitHub Actions et Google Sheets non lancés ici.
