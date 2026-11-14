# Un seul moteur de synchronisation Google Sheets

`pmu_geny/moteur_sheets.py` est l'unique implémentation d'authentification,
lecture, planification, écriture et contrôle des publications vers Sheets.

## Deux déclencheurs, les mêmes règles

- Le cycle PMU appelle `SynchroniseurSheets.synchroniser_cycle()`.
- Le collecteur d'historiques réutilise une instance par passage et appelle
  `synchroniser_cheval(..., include_kpi=False)` après chaque sauvegarde durable.
- Les KPI sont consolidés une fois à la fin du passage. Si cette consolidation
  échoue, elle est reprise sans recollecter ni republier les chevaux réussis.
- `scripts/synchroniser_un_historique.py` n'est plus qu'un adaptateur de
  compatibilité. Il ne contient aucune logique HTTP, de dédoublonnage ou d'écriture.
- `sync_google_sheets.py` conserve les transformations des données, le planificateur
  testé et la lecture paginée ; son point d'entrée délègue au moteur commun.

Le périmètre cheval ne publie que son historique et ses métadonnées de disponibilité.
Le périmètre cycle publie aussi les prévisions et les résultats. Les droits de
modification des colonnes et les formules KPI restent inchangés.

## Concurrence et reprise

Les deux workflows conservent `pmu-donnees-production`, sans annulation d'un
traitement en cours. Ce verrou protège les runners GitHub distincts ainsi que
les écritures sur `pmu-data`. Un verrou local par identifiant de fichier empêche
également deux processus locaux d'écrire simultanément sur le même registre.
Ces verrous couvrent les chemins automatisés du projet, pas les outils externes
ou les modifications manuelles de l'utilisateur.

Le moteur relit les données à chaque opération : aucune copie distante supposée
à jour n'est réutilisée entre deux publications de chevaux. La session HTTP et
ses connexions sont réutilisées, sans mettre les lignes en cache.

Un échec d'écriture arrête l'opération ; aucun ajout ne suit une mise à jour
refusée. Une réponse perdue après un ajout n'entraîne pas de réessai aveugle :
la reprise relit les clés et retrouve l'ajout éventuellement déjà accepté.
Les écritures de plusieurs onglets ne sont pas une transaction atomique ; la
reprise est idempotente. L'historique est vérifié avant publication des autres
onglets afin de bloquer au plus tôt les anomalies d'intégrité.

Les contrôles de la PR #12 restent actifs : lecture complète, inventaire indépendant
des clés, refus des copies et ajouts incohérents, seuil de croissance, vérification
après écriture, journaux et échec explicite en cas de blocage.

## Mesure de l'optimisation

Une simulation hors réseau sur trois chevaux compare trois publications autonomes
à un passage utilisant une session partagée et une consolidation finale :

| Mesure | Publications autonomes | Passage partagé |
|---|---:|---:|
| Sessions Google créées | 3 | 1 |
| Lectures de l'onglet KPI | 3 | 1 |
| Appels API simulés au total | 30 | 27 |

Le contenu final est identique. Cette mesure documente une réduction des appels ;
elle ne constitue pas une garantie sur le temps réel, qui dépend aussi des sources
et des temps de réponse Google. Le moteur journalise les lectures, écritures et
durées par périmètre pour observer son comportement en production.
