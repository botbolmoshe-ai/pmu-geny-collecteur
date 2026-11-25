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


## Observation de production du 25 novembre 2026

Les heures de cette section sont exprimées en Europe/Paris. L’inventaire a été
relevé avant les exécutions de remise en service. Les 22 exécutions avaient
toutes une première et unique tentative, des journaux ZIP récupérés et des
métadonnées de jobs relues. Six exécutions étaient planifiées, dix venaient d’un
dispatch, quatre d’une PR et deux d’un push. Vingt et une ont abouti. Une a
échoué après la synchronisation réussie de Sheets. Aucun run de cet inventaire
n’a été annulé. Le délai ci-dessous est mesuré de la création au démarrage du
job effectivement exécuté. Il inclut la mise en file et l’attribution du
runner. Un cron sans run ne fournit aucune trace de file exploitable par
l’API GitHub.

| Création | Workflow | Événement | Délai max des jobs | Conclusion |
| --- | --- | --- | --- | --- |
| 00:40:02 | [Validation](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/actions/runs/45511884325) | pull_request | 2 s | Succès |
| 00:40:02 | [Dashboard](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/actions/runs/45511884225) | pull_request | 2 s | Succès |
| 01:45:34 | [Validation](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/actions/runs/45520574890) | pull_request | 2 s | Succès |
| 01:45:34 | [Dashboard](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/actions/runs/45520574901) | pull_request | 1 s | Succès |
| 02:34:16 | [Historiques](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/actions/runs/45526713519) | schedule | 2 s | Succès |
| 04:32:27 | [Historiques](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/actions/runs/45540684448) | schedule | 2 s | Succès |
| 04:48:30 | [PMU](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/actions/runs/45542496523) | schedule | 2 s | Succès |
| 11:06:35 | [PMU](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/actions/runs/45591785406) | workflow_dispatch | 2 s | Échec de certification |
| 11:46:55 | [Dashboard](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/actions/runs/45598245330) | push | 2 s | Succès |
| 11:46:55 | [Validation](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/actions/runs/45598245265) | push | 2 s | Succès |
| 11:47:05 | [PMU](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/actions/runs/45598270407) | workflow_dispatch | 2 s | Succès |
| 11:47:44 | [Validation](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/actions/runs/45598371426) | workflow_dispatch | 76 s | Succès |
| 11:47:46 | [Validation](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/actions/runs/45598375949) | workflow_dispatch | 105 s | Succès |
| 11:56:14 | [PMU](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/actions/runs/45599692287) | workflow_dispatch | 2 s | Succès |
| 12:00:15 | [Historiques](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/actions/runs/45600297537) | workflow_dispatch (relais) | 1 s | Succès |
| 12:09:17 | [Validation](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/actions/runs/45601750911) | workflow_dispatch | 2 s | Succès |
| 14:31:43 | [Historiques](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/actions/runs/45624502210) | schedule | 3 s | Succès |
| 14:32:11 | [PMU](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/actions/runs/45624582498) | workflow_dispatch (relais) | 2 s | Succès |
| 14:38:51 | [PMU](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/actions/runs/45625723001) | schedule | 2 s | Succès |
| 18:05:35 | [Historiques](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/actions/runs/45661005767) | schedule | 1 s | Succès |
| 18:06:01 | [PMU](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/actions/runs/45661083315) | workflow_dispatch (relais) | 3 s | Succès |
| 19:41:08 | [PMU](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/actions/runs/45677658386) | workflow_dispatch | 3 s | Succès |

### Causes et preuves

| Obligation | Observation et cause | Correctif et contrôle |
| --- | --- | --- |
| H-3 / H-2 | Aucun run PMU de 04 h 48 à 11 h 06. Chartres H-3 manqué (08 h 25), H-2 lu à 11 h 07 pour 09 h 25. La R4 a publié à 11 h 07 et 11 h 48 pour des échéances initiales de 11 h 12 et 12 h 12. Les modifications PMU d’horaires pouvaient relancer un jalon figé pour le même inventaire. | Conserver le certificat et son heure de référence. Le lecteur vérifie les preuves aux deux horaires quand l’identité et le programme d’origine sont attestés. Aucune reprise ne recrée un H-3 ou un H-2 à l’heure. |
| Arrivées | Les deux flux PMU donnent les rangs 1, 1, 3 (4, 6, 8) pour Chartres C3 et 1, 2, 2 (5, 2, 6) pour C5. Le parseur rejetait les groupes de rang et les rangs répétés. | Conserver les rangs ex æquo, vérifier la concordance du programme définitif et des participants, rapprocher toujours à dernière course +30 min. Un podium de plus de trois chevaux demeure exclu de la comparaison TOP3. |
| Évaluation ML | Douze arrivées sur treize ne présentaient pas de paire recevable depuis le changement d’horaire PMU. | Récupérer la preuve du programme d’origine à partir de `d0f654ac` et `e21d0674` sur `pmu-data`. Vérifier identité de course, empreinte, chronologie et relecture Sheets. Une paire existante reste immuable, avec le même seuil anti-fuite. Le rejeu donne 15/15 paires H-2 après récupération des deux arrivées. |
| Global | Checkpoint à 11 h 58, dernier KPI observé vers 19 h 42. Le secours global de 14 h 32 a bifurqué vers un jalon R4 à la suite du changement d’horaire. Les derniers runs ont publié des résultats, sans exécuter le global. | Rapprocher puis avancer le global s’il est dû avec relecture des deux programmes capturés dans le cycle. Prioriser un jalon pré-départ nouvellement révélé. Une consolidation KPI seule ne fait pas avancer le global. |
| Incrémental / fond | Les historiques n’ont reçu que cinq runs, dont deux relais vers PMU. À 02 h 35, un 403 Geny a suspendu les deux files. Le run de 04 h 32 a traité les deux files. À 12 h 00, 11 captures et synchronisations confirmées. Le checkpoint de préparation à 12 h 08 est limité aux partants à venir (24/149 J et 25/198 J+1). | La réservation du jour utilise la marge opérationnelle de 8 min et le niveau de priorité effectif du global. Le recensement manuel libère le verrou par tranches de 7 min et reprend hors verrou. Le secours distingue le dernier succès d’un échec et maintient le verrou commun. Les pauses Geny et la cadence adaptative restent communes aux files. |
| Déclencheurs | Deux seuls runs PMU planifiés sur l’inventaire, dont un tick léger nocturne. Le secours historique a émis deux dispatchs et PMU a relayé les historiques à 12 h. Les deux jobs de migration ont attendu jusqu’à 105 s. Les jobs PMU pris individuellement ont démarré avec 2 à 3 s de délai. | Conserver les deux relais et le verrou d’écriture. L’API ne donne pas la cause d’un événement schedule jamais matérialisé. La surveillance externe sert à signaler cette perte. |

Les archives des quatre workflows exécutés ont été consultées. Les deux autres
workflows présents dans `main`, rattrapage dédié et migration Geny, restent
manuels et sous le même verrou. Le marqueur de production n’a déclenché
aucun run de référence. La validation de la migration Google Sheets a occupé
le verrou à la demande. La validation hors ligne et le tableau de bord
indépendant ne prennent pas le verrou.

### Rejeu

La recette 48 h supplémentaire parcourt 192 ticks virtuels. Une absence de
cron de six heures, une annulation explicite, deux arrivées ex æquo et deux
relectures Sheets incomplètes sont injectées. Elle appelle réellement le
planificateur, le cycle, le parseur PMU, les calculateurs, la construction
des lignes, le contrôle des résultats et la certification. Les transports
PMU et Sheets sont simulés et les sockets sont fermés. Les régressions
dédiées contrôlent notamment Geny 403/429 et la cadence, la persistance,
les reprises après conflit, les dates et les changements d’heure, le ML
et l’IPR. Les résultats prospectifs et les signaux de relance restent à
confirmer sur les prochaines échéances réelles.
