PMU GENY V15 - Vincennes R2C8 Prix de Beauvais - 10/11/2026
================================================================
Course Geny ID: 1697377
URL: https://www.geny.com/course/1697377-2026-11-10-vincennes-prix-de-beauvais/partants-pronostics
18 chevaux declares dans la liste Geny, dont n°8 Ma Belle Attaque signale non-partant.
L'horaire selon les sites n'est pas parfaitement homogene : verifier sur PMU officiel.

INSTALLATION
1. Dezipper, copier le CONTENU du dossier pmu_v11_complet a la racine du depot Github.
2. GitHub Desktop: Commit to main, Push origin.
3. Actions > PMU - V15 Vincennes R2C8 Prix de Beauvais (manuel) > Run workflow.
4. Laisser l'URL par defaut; max_chevaux = 18.
5. Lire artifact 'bilan-pmu-v15-r2c8-beauvais', resultats/bilan.json.

MODIFICATIONS
- Workflow V15 distinct de l'ancien pilote R2C1 (conserve pour reference).
- URL R2C8 et ID course 1697377 valides, decouverte des 18 declarations.
- Test simple possible avec max_chevaux=3, puis run complet avec 18.
- Cache GitHub Actions separe pmu-v15-beauvais-, fichiers de bilan par GENY-1697377.
- Reprend tout le code V14, incluant controles 403 / 429, qualification et rangs.
- 403/429 suspend la collecte Geny seulement.
- Le n°8 doit etre exclu des pronostics si NP confirme sur PMU; ce workflow ne calcule pas de TOP3.
- La presence de 18 lignes dans le DOM et l'acces aux 18 fiches sont a valider sur Github.
- Aucune ecriture Google Sheets.
- Le cache GitHub Actions n'est pas un stockage durable garanti.
