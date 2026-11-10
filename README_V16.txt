PMU V16 - DECOUVERTE SEPAREE / COLLECTE INCREMENTALE / STOCKAGE GIT DURABLE
============================================================================
INSTALLATION
- Copier le CONTENU du dossier pmu_v16 a la racine du depot GitHub.
- GitHub Desktop: Commit to main puis Push origin.
- Actions > PMU - V16 Decouverte et collecte incrementale > Run workflow.

PREMIERE EXECUTION PAR COURSE
1. mode = decouvrir ; course_url = URL officielle Geny ; nombre_partants = nombre de lignes Geny.
   Lancement decouverte seulement. Enregistre le manifeste sur branche pmu-data.
2. mode = collecter ; memes course_url / nombre_partants ; max_chevaux = nombre vise.
   Charge le manifeste depuis pmu-data. Ne reconsulte PAS la liste des partants.
3. Les executions suivantes en mode collecter reemploient les historiques complets.
   Un cheval deja COMPLET n'engendre aucune requete Geny, y compris dans une nouvelle course.

CONSERVATION
- Branche 'pmu-data' creee automatiquement via GITHUB_TOKEN si le depot l'autorise.
- Fichiers de donnees : etat_persistant.json, historiques/{id}/historique_geny.*, manifestes/GENY-{id}.json.
- Verifier que GitHub Actions a les permissions d'ecriture sur le depot. Le push peut etre interdit
  par la protection de branche ou la politique de permissions du depot.
- IMPORTANT : ne pas lancer en parallele les anciens workflows V11/V15 (leurs caches ne sont
  PAS importes automatiquement). Les anciens artefacts d'historiques ne sont pas automatiquement
  presents dans la nouvelle branche ; s'ils sont disponibles il faudra les migrer.

PROTECTIONS ET LIMITES
- Code 403/429 reconnu meme sous HTTP 200 ; arret sans nouvel essai Geny.
- Cooldown local 1h conserve dans pmu-data ; aucune requete Geny pendant ce cooldown en collecte.
- 1h est une politique prudente, PAS une limite officielle publiee par Geny.
- Un blocage pendant decouvrir ou collecter declenche un cooldown commun de 1h.
- Le workflow ne consulte pas PMU officiel pour valider les non-partants ; si un NP est
  annonce, il doit etre EXCLU du TOP3 par la chaine de pronostics a venir.
- La liste du manifeste est un instantane ; une nouvelle course necessite un nouveau manifeste.
- Aucune ecriture Sheets, aucun calcul TOP3 et aucune planification ne sont implementes.

EXEMPLE TEST EXISTANT
- Course du 10/11/2026 Vincennes R2C8 : ID 1697377 / 18 declares.
- Les resultats sont separes par GENY-1697377.
- Regarder les logs, les artefacts et la branche pmu-data apres chaque phase.
