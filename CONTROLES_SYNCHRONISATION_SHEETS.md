# Contrôles de synchronisation de l'historique

## Cause de l'incident

La lecture générale s'arrêtait à la ligne 5 000, alors que les ajouts n'étaient
pas limités à cette zone. Les clés déjà présentes plus bas étaient réinsérées
aux passages suivants. Le nettoyage du 14 novembre a supprimé 158 245 copies
strictement identiques, conservant 15 473 lignes distinctes et les annotations.
Les tests initiaux de synchronisation individuelle n'avaient pas couvert cette
interaction avec le cycle général sur une feuille de plus de 5 000 lignes.

La lecture paginée complète et la conservation des variantes ont été corrigées
dans les PR #10 et #11. Un HTTP 200 n'est plus une preuve suffisante d'intégrité.

## Avant toute écriture de l'historique

Les deux synchroniseurs utilisent le même garde-fou :

1. Vérification des clés source, non vides et non répétées.
2. Comparaison de la lecture des lignes avec une lecture indépendante de la
   seule colonne des clés, sur toute la hauteur déclarée de l'onglet.
3. Blocage si des copies de valeurs identiques sont déjà présentes. Aucune
   suppression automatique : les éventuelles annotations restent à examiner.
4. Ajouts limités exactement aux nouvelles clés source : une clé présente ne
   peut pas figurer dans les lignes à ajouter, même avec un plan erroné.
5. Blocage d'une croissance supérieure au maximum de 500 lignes ou de 10 % des
   clés existantes par synchronisation. Le rattrapage individuel peut continuer
   progressivement ; une importation massive doit être préparée séparément.

Un import initial volumineux dans une feuille vide peut être explicitement
identifié dans une exécution manuelle avec `PMU_SHEETS_IMPORT_INITIAL=1`.
Ce réglage n'est activé dans aucun workflow automatique.

## Après écriture

Relire la feuille avec ses dimensions actualisées. Vérifier exactement les clés,
leurs multiplicités et le nombre attendu de lignes. Toute disparition, ajout
inattendu ou copie de valeurs provoque un échec visible. Les variantes existantes
ayant une même clé restent protégées contre un arbitrage automatique.

## Signalement et preuve

Chaque contrôle écrit `AUTORISE`, `VALIDE` ou `BLOQUE` dans les journaux, le résumé
GitHub Actions et `resultats/synchronisation/controles.jsonl`, archivé en artefact.
Un blocage produit une annotation d'erreur et un échec du traitement. Le worker
conserve l'historique déjà collecté et son état de reprise avant de s'arrêter.
Il ne passe pas silencieusement aux chevaux suivants après un incident d'intégrité.

Ces contrôles couvrent les synchroniseurs automatisés. Ils ne constituent pas une
contrainte d'unicité du serveur Google Sheets contre des écritures manuelles ou
des outils externes. Une base PostgreSQL permettrait d'ajouter cette contrainte
au niveau du stockage, tout en conservant explicitement les versions légitimes.
