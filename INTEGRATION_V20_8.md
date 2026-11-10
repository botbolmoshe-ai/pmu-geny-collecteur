# V20.8 — raccordement bout en bout

## Ce qui est réalisé
- V20.7 complète conservée : données PMU et Geny, modèles, exports, audits, historique durable.
- Synchronisation idempotente du cache exporté vers le Google Sheet existant (3 onglets).
- Une étape GitHub Actions après la sauvegarde de `pmu-data`.
- Aucun effacement ni réinitialisation de cellule. Les valeurs absentes ne suppriment rien.
- Les cotes restent *hors* des variables Machine Learning.

## Configuration à faire une seule fois
1. Sur Google Cloud, créer un projet gratuit et activer **Google Sheets API**.
2. Créer un **compte de service** et télécharger la clé JSON (à conserver secrète).
3. Dans le Google Sheet existant, cliquer **Partager**, ajouter l'email `client_email` de la clé comme **Éditeur**.
4. Dans GitHub > dépôt > **Settings > Secrets and variables > Actions > New repository secret**, créer **GOOGLE_SHEETS_SERVICE_ACCOUNT_JSON** contenant la totalité de la clé JSON.
5. Copier le dossier `pmu_v20_8` dans le dépôt (sur `main`), Commit, Push, puis exécuter `auto`.
6. Vérifier la ligne `SYNC_GOOGLE_SHEETS` dans GitHub Actions et les trois onglets.

## Attention aux limites actuelles
- Le connecteur ne compense pas une course sans manifeste Geny : les lignes apparaissent quand les exports existent.
- Si GitHub signale `SYNC_GOOGLE_SHEETS=NON_CONFIGURE`, l'étape est ignorée : absence de secret.
- La tâche ChatGPT existante n'est pas automatiquement reconfigurée par ce package. Sa configuration doit être adaptée pour lire le registre Google Sheets, sans refaire les collectes.
- La validation de bout en bout sur le GitHub privé nécessite un lancement réel de ton côté.

## Protocole de supervision ChatGPT
Source unique : `PMU — TROT | Registre unique TOP 3` (Google Sheets, id ci-dessus).
Pour chaque cycle : vérifier les nouvelles lignes et anomalies, ne jamais recalculer les TOP3 lorsque GitHub les a déjà produits.
Avant départ : transmettre uniquement les TOP3 figés et horodatés, mentionner les NP et le statut ML.
Après course : comparer TOP3 initial, TOP3 final, ML, arrivée et cotes ; signaler l'absence de données comme indisponibilité, jamais comme zéro.
Ne jamais publier un pronostic après le départ théorique ou officiel.
Un rapport quotidien résume la couverture et les écarts.
