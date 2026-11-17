# Orchestration, historiques et échéances H-2/H-1

Les trois points d'entrée conservent un seul moteur de collecte et le même verrou
`pmu-donnees-production`. La file GitHub utilise désormais `queue: max` avec
`cancel-in-progress: false` : plusieurs demandes peuvent attendre sans que la
nouvelle remplace la précédente. GitHub limite cette file à 100 demandes ;
l'ordre d'attente est pris en compte, pas une priorité métier absolue.

Référence officielle consultée le 17 novembre 2026 :
https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/control-workflow-concurrency

## Cadence et priorité

- PMU : contrôle de plan toutes les quinze minutes. Un cycle global reste dû
  toutes les heures ; entre deux cycles, seules les courses dont un jalon est dû
  sont rafraîchies. Un tick sans travail évite installations, réseau et Sheets.
- Historiques : départs prévus aux minutes 5, 20, 35 et 50 ; budget de sept
  minutes par passage. Contrôle de pause et de priorité avant de charger le
  navigateur. Une publication à reprendre peut continuer sans nouvelle requête
  Geny pendant une pause. Le worker cède entre deux chevaux lorsqu'un cycle PMU
  devient dû, même si le cron est en retard.
- Fond : minute 12, quota d'un cheval et budget de deux minutes. Il conserve
  les règles d'attente et de protection des prochains partants.

Ces budgets augmentent le temps utile disponible, sans réduire la pause réseau
de trente secondes entre deux chevaux ni modifier les délais 403/429. Les gains
de débit réels doivent être mesurés ; un refus externe peut toujours les limiter.

## Échéances et preuve de publication

Pour chaque course du jour, H-2 et H-1 ouvrent une fenêtre de préparation trente
minutes avant leur échéance. Le plan reste dû jusqu'à publication des deux TOP3.
Les jalons acceptent le ML expérimental explicitement identifié, sans prétendre
que ses scores sont calibrés.

La certification intervient après une synchronisation Sheets réussie et vérifie
les trois numéros uniques, le contexte de course, les horaires, les profils PMU
frais, les non-partants et la chronologie du candidat ML expérimental. Une copie
immuable de chaque version d'un jalon est conservée avec son empreinte SHA256.
Une publication tardive reste marquée tardive ; aucun jalon pré-départ n'est créé
après le départ. Un échec Sheets, un TOP3 invalide ou un jalon incomplet/tardif
rend le contrôle strict en échec ; ses preuves restent sauvegardées et archivées.

Les certificats dans `publications/` attestent les versions effectivement envoyées
avant départ. Les preuves H-2/H-1 sont dans `jalons/`. Le dernier contrôle est
dans `qualite/dernier_controle_production.json`. Les prochaines versions peuvent
évoluer avant départ sans réécrire ces copies.

La sauvegarde avant Sheets doit réussir avant toute publication. La sauvegarde
des contrôles après Sheets conserve les mêmes règles, sans force push ; un
conflit distant arrête la sauvegarde au lieu d'écraser une autre version.

GitHub cron fonctionne au mieux de sa disponibilité : ces marges et contrôles
ne garantissent pas une exécution à la seconde. Un déclenchement trop tardif est
mesuré et doit rester visible, pas être présenté comme un jalon tenu.

## Réutilisation des liens Geny déjà observés

La première page de course vérifiée peut fournir plusieurs liens de chevaux via
les liens du tableau ou les données structurées de la même course. Le worker
mémorise ces preuves, sans ouvrir de fiche supplémentaire, puis les réutilise
avec concordance du nom, du numéro, de la course et une fraîcheur de 24 heures.
Une ambiguïté ou un lien absent conserve la résolution individuelle existante.

Un lien ne valide ni l'identité finale ni la carrière : la fiche, le nom attendu
et l'historique restent contrôlés avant acceptation. Les preuves survivent aux
checkpoints ; les pauses partagées s'appliquent aussi aux liens mémorisés.
