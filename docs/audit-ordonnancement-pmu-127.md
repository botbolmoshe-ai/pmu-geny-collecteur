# Ordonnancement PMU — ticket 127

## Audit

Le rapprochement arrive à échéance 30 minutes après le dernier départ de
chaque réunion. Le plan savait signaler simultanément un jalon et un
rapprochement. L'ancien cycle ne traitait les résultats qu'en mode
`RAPPROCHEMENT`. Le correctif repris faisait aussi le calcul, mais le
périmètre Sheets de `JALONS` et la certification ignoraient ces résultats.

| Obligation | Déclencheur et précondition | Exécution et preuve | Reprise / alerte |
| --- | --- | --- | --- |
| Global PMU | Cron UTC 7/22/37/52, dispatch, marqueur, secours historique ; fenêtre globale 07–21 Paris | Programme J et J+1, consolidation et vérification Sheets | État global avancé avec deux programmes frais ; secours après deux heures |
| Préparer J+1 | Plan nocturne, programme ou partants manquants | Captures de programme et partants, sans certification pré-départ | Diagnostic durable et nouvel essai borné |
| H3/H2 | Créneau de la réunion avant le premier départ, y compris avant 07 h | Prévisions et lecture de l'onglet Courses ; preuve figée par méthode | Échec ou retard explicite ; aucune certification rétroactive |
| Résultats | Dernière course de la réunion +30 min, y compris en soirée | Arrivée officielle vérifiée, écriture puis relecture par réunion | Réécriture idempotente après échec Sheets ; reprise ciblée des résultats provisoires |
| NP, marché, IPR | Relevé pré-départ avec partants cohérents | Règles de fraîcheur existantes et IPR en observation | Réutilisation régie par le moteur PMU ; pas de score inventé |
| Apprentissage ML | Publication puis cycle de résultats, hors créneau nocturne automatique | Entraînement et qualification existants ; aucun changement de seuil | Empreinte d'entraînement et réexécution idempotente |
| Historiques incrémentaux | Cron Paris, dispatch ou relais PMU ; priorité aux échéances | Checkpoint puis publication par cheval | Cooldown partagé, relance locale par clé et secours PMU si dû |
| Rattrapage global Geny | Dispatch et budget nocturne de l'incrémental | Inventaire et checkpoint sous verrou | Conservation de la file et des délais ; le relais ne contourne pas les refus |
| Migration historique Geny | Dispatch explicite sur main | Sauvegarde puis relecture intégrale | Nouveau passage idempotent sous verrou |
| Validation itérative | Push, PR, dispatch | Suites hors ligne et rapports ; migration des dates explicitement sélectionnée | Le job de migration prend le verrou de production |
| Validation dashboard | Push, PR, dispatch | Tests UI en lecture seule | Le test Streamlit sur registre réel relève du workflow de validation itérative |

Les workflows d'écriture partagent `pmu-donnees-production`, sans annulation du
run actif. Le rapprochement complémentaire replanifie les obligations
échues pendant l'exécution. Les preuves de résultats sont contrôlées par
réunion même lorsqu'un jalon échoue à son SLA. La consolidation KPI est
conditionnée à la certification. Les preuves et diagnostics restent
persistés après un échec fonctionnel.

GitHub Actions confirme des exécutions planifiées et un secours par dispatch
sur le dépôt. La cause des ticks absents le 24 novembre n'est pas exposée
dans les métadonnées des runs observés. Le secours existant par le workflow
d'historiques couvre la perte du seul déclencheur PMU lorsque le déclencheur
historique se présente. Les deux restent tributaires de GitHub Actions.

## Recette

Le scénario intégré utilise deux journées dans une fenêtre de 48 h en
horloge virtuelle. Chaque journée comprend une collision H2/résultats,
une arrivée officielle par course, un résultat absent lors de la relecture
Sheets, puis une reprise soixante minutes plus tard. Les assertions vérifient
le seuil de 30 minutes, le périmètre des deux onglets, l'absence de fausse
certification, l'absence de nouvel appel PMU pour un résultat déjà capturé,
la conservation du premier horodatage et la disparition de la tâche après
publication prouvée. Un second scénario vérifie H3 avant 07 h et le signal
envoyé au secours historique.

Les suites existantes complètent cette recette pour la cadence Geny, les
reprises de publication, les transitions horaires, les gardes de fraîcheur,
la persistance, l'immuabilité des jalons et les commandes des relais. La
recette intégrée ne rejoue pas toutes les combinaisons d'incidents ni le
service Github Actions lui-même. Elle ne remplace pas l'observation du
premier chevauchement réel après déploiement.
