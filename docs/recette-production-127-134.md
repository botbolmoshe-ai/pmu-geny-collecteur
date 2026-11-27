# Recette de production des tickets #127 et #134

Les décisions du 27 novembre 2026 s’appliquent à tous les lots. Les prévisions pré-départ et leurs certificats restent datés et immuables. Les rapprochements restent dus 30 minutes après la dernière course maintenue de chaque réunion.

[Décision #127](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/issues/127#issuecomment-7215161963) · [Décision #134](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/issues/134#issuecomment-7215162632)

## Référence avant refactorisation

Les runs créés du 25 novembre au 27 novembre, jusqu’au contrôle du 27 à 09 h 53 UTC, comptent 48 exécutions, 45 succès et trois échecs. Les trois échecs sont localisés à la certification PMU. Le run du 26 à 14 h 23 UTC a écrit dans Sheets et a signalé huit jalons de course en retard et un jalon de réunion en retard. Aucune annulation n’est enregistrée dans ce périmètre.

- Les 20 jobs PMU observés démarrent en médiane 3 s après la création du run, au plus en 7 s. L’intervalle maximal entre deux créations PMU est de 7 h 58 min 31 s, le 26 entre 04 h 33 et 12 h 32 UTC. Les événements absents ne permettent pas d’établir la cause des crons manqués.
- Les 15 jobs historiques durent en médiane 7 min 54 s, au plus 16 min 14 s. Le verrou de production couvre alors les accès Geny, les attentes de cadence, les checkpoints et les écritures Sheets.
- Le registre affiche 262 arrivées vérifiées pour 251 courses de référence avant le premier déploiement. Les numérateurs proviennent de Résultats & Analyse, tandis que l’ancien dénominateur provient uniquement de Courses & Prévisions.
- Le bilan nocturne du 27 à 03 h 06 UTC confirme dix carrières, 734 performances et 110 requêtes Geny, dont 10 documents et 20 fetch. Le cache HTTP a servi 520 ressources. Le passage du 26 comptait 550 requêtes pour neuf carrières et 459 performances. Ces passages réels portent sur des cohortes différentes et précèdent cette refactorisation.
- Le bilan du 27 compte 1 362 cibles complétées sur 2 584 et 749 contextes distincts sans ID, dont 693 avec course et 56 sans course. Ces deux catégories signifient absence de preuve locale. Elles ne prouvent ni une recherche négative ni une fiche inaccessible.
- Les 20 cibles restantes du lot fixe ont chacune un ID recensé et une URL candidate. L’état durable ne contient pour elles ni carrière complète, ni motif d’échec constaté, ni délai de reprise. Dans la file nocturne, la priorité du lot venait après la disponibilité d’un lien déjà vérifié et l’urgence du départ. La nouvelle priorité s’applique après les partants protégés J/J+1 et avant les autres carrières du stock à identité connue.

[Historique Actions](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/actions) · [Run de certification en retard](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/actions/runs/45838605938) · [Bilan nocturne](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/95ecbee82f53d268228f1ae2d1bbe42315b41f14/rattrapage_historiques/bilan.json)

## Obligations suivies

| Obligation | Déclencheur | Entrée et exécution | Preuve et reprise |
| --- | --- | --- | --- |
| Programme PMU J/J+1 | Cycle global, préparation nocturne ou actualisation légère du programme J | Programme PMU horodaté, partants si nécessaires à la préparation | Programme et diagnostic durables. Reprise au prochain tick. Secours si la fraîcheur du programme J atteint 30 min |
| H-3/H-2 et non-partants | Échéance calculée par réunion | Partants PMU observés, calcul Direct et ML sur les preuves disponibles | Relecture Sheets, version gelée et statut ponctuel, tardif ou incomplet. Aucune correction rétroactive du figement |
| Arrivées H+30 | Dernière course maintenue de la réunion +30 min | Inventaire confirmé et arrivée officielle PMU | Certificat de rapprochement et relecture Sheets, puis reprise d’un incomplet même si la date a changé |
| Identités et historiques Geny | Passage incrémental, puis créneau de stock | Partants J/J+1 prioritaires, index et liens validés, puis carrières et ferrures | Délais persistants, réserve partagée, refus 403/429 et Retry-After, checkpoint de capture avant publication |
| Publication Geny de jour | File durable du passage incrémental indépendant | Dernière révision pmu-data, écritures sous le groupe commun à tous les writers Sheets | Contrôle des clés et de la relecture. Reprise de la capture au passage suivant, y compris sous cooldown Geny |
| Publication globale PMU | Cycle global | Courses & Prévisions et Résultats & Analyse | Relecture des preuves PMU puis KPI. Le chemin manuel préserve la consolidation historique |
| Modèle ML et IPR | Cycle de résultats et règles de maturité existantes | Prévisions produites à partir de preuves datées et cotes informatives séparées | Preuves de révision et de promotion. Le programme et les arrivées restent traitables si l’installation ML échoue |

## Mesures et recette

| Mesure | Avant | Après |
| --- | ---: | ---: |
| Écriture d’un fichier depuis un snapshot de 10 766 fichiers, trois essais locaux par variante, médiane | 3,47 s | 1,12 s |
| Résolution locale de l’association course Geny dans la préparation de 179 partants sur 15 courses, même snapshot et rapport identique | 179 appels | 15 appels |
| Dénominateur des arrivées, recalculé sur le même snapshot pmu-data du cycle PMU du 27 | 269 | 287 |
| Arrivées vérifiées sur ce snapshot | 262 | 262 |

La recette hors réseau couvre une collision jalons/arrivées, deux jours virtuels, un trou de six heures dans les ticks, une course annulée, un ex æquo, le refus d’une certification sans relecture, une panne Sheets puis la reprise sans acquisition, le cooldown et l’idempotence. Les tests Git reproduisent deux producteurs partant du même état, une avancée distante pendant le push et un conflit sur le même chemin.

Le run PMU pilote du 27 confirme l’écriture pmu-data, la synchronisation Sheets, la certification et la consolidation des KPI. La lecture directe de Résultats & Analyse confirme les huit arrivées de Vincennes du 24 novembre. Les scores ML relus de R3C6, R3C7 et R3C8 sont 0, 0 et 2 sur 3.

Le passage indépendant du 27 a validé cinq carrières en 86 requêtes Geny, sans 403 ni 429. Le job Sheets a relu les cinq carrières et leurs 165 nouvelles performances, sans erreur ni publication restante dans la file incrémentale. Le registre affiche 39 097 performances après ce passage.

[Run PMU pilote](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/actions/runs/45978869432) · [Premier run Geny après changement des index](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/actions/runs/45979321774) · [Passage Geny indépendant](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/actions/runs/45980746217) · [Résultats publiés](https://docs.google.com/spreadsheets/d/1BjzDzC6NsLRMax2XjrCIcCIIgz6hyCJ1YTWOa5hiGLo/edit#gid=810005)

## Déploiement et retour arrière

La PR #137 fournit la base de publication Git. La PR #139 ajoute le chemin indépendant de jour derrière le paramètre manuel acquisition_independante. Après recette réelle, ce chemin est activé par défaut pour les crons de jour et les relais PMU de jour. La variable GENY_ACQUISITION_INDEPENDANTE à false redonne le chemin historique aux déclenchements automatiques. Revert des commits par ordre inverse en fenêtre calme si nécessaire. Les anciens instantanés pmu-data et les captures en attente utilisent le même schéma.

Les accès manuels et le stock nocturne conservent la sérialisation historique. L’observation de deux journées réelles, la couverture intégrale de l’échantillon comparatif Geny et la mesure du respect des objectifs de service restent nécessaires pour clôturer les tickets. Les domaines de recherche Geny soumis à autorisation gardent les contrôles existants. Aucun résultat nominatif n’est déduit de l’absence de preuve locale.

## Reprise du 27 novembre après la PR #142

La branche `fix/127-134-138-autonomie-supervision` et la [PR #143](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/pull/143) reprennent le travail après `f202852e` et la suppression du workflow de migration dans `cecc2239`. Les cinq fichiers actifs conservent leur chemin et les clés de jobs de validation restent identiques. La migration de structure du 24 novembre a été appliquée et relue. Son ancien point d’entrée a été supprimé. Les parseurs, le contrôle de schéma et la recette historique restent disponibles. [Preuve de migration](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/actions/runs/45434020426)

Le 27 novembre, le cycle global a été relu à 11:27:26. À 14:16, cette preuve avait environ 2 h 49. Le cycle de 13:04 a publié les jalons, et Geny a poursuivi son acquisition et sa publication. Lorsque les jalons étaient dus, l’exécution choisissait le chemin ciblé. Même lorsqu’elle commençait en mode global, l’actualisation du programme pouvait réduire le périmètre aux jalons et empêcher l’acquisition de J+1. Le global conserve désormais son périmètre et les courses de jalon sont placées en tête du calcul. Le secours du workflow incrémental peut demander le global dès son échéance, sous les gardes existantes de relai et de dédoublonnage. [Cycle global](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/actions/runs/45982023309) · [Cycle jalons](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/actions/runs/45995585816)

Les preuves de relecture de `Courses & Prévisions` et `Résultats & Analyse` sont persistées séparément avant la certification. Le global progresse seulement après une acquisition fraîche de J et J+1 pendant le cycle et la confirmation des deux publications. Le rapprochement garde la règle du dernier départ de chaque réunion +30 minutes. Son checkpoint et ceux du jalon, de l’arrivée observée et de la dernière publication PMU sont indépendants.

Le passage Geny nocturne de rattrapage est programmé dans le workflow 03, aux minutes 27 et 57 de 21 h à 07 h, heure de Paris. Le workflow 02 garde la priorité des partants et traite sa file incrémentale aux minutes 12 et 42. Le passage de rattrapage revalide son budget avant et après l’installation du navigateur, puis applique les gardes métier et le cooldown déjà partagés. Le verrou d’écriture Sheets reste commun. GitHub peut retarder ou omettre un tick. Les échéances PMU, les preuves durables et le relai de secours pilotent la reprise au passage suivant.

### Mesures

| Contrôle | Résultat |
| --- | --- |
| Trois heures consécutives avec jalons dus | 3 cycles globaux sur 3 avec acquisition J/J+1 et checkpoint indépendant dans la recette. L’ancien chemin ciblé ne lançait pas J+1. |
| Panne Sheets sur le périmètre Résultats | Le jalon relu reste certifiable. Le global et les rapprochements sans preuve reprennent au passage suivant. |
| Identités, 30 cibles avec ID dans le stock | 28 confirmations locales, 2 sans preuve suffisante. |
| Identités, 30 cibles sans ID dans le stock | 2 confirmations locales, 28 sans tentative établie. |
| Dernier passage nocturne archivé | 10 carrières complètes et 734 performances, 110 requêtes réseau et 520 ressources servies du cache. |
| Comparaison des passages nocturnes des 26 et 27 novembre | 61,1 puis 11,0 requêtes par carrière. Les chevaux diffèrent. Cette comparaison décrit les passages observés. |
| Stock et lot de référence | 1 362 cibles complétées sur 2 584. 76 cibles publiées sur 96. 749 contextes distincts sans preuve locale, dont 693 avec course et 56 sans course. |

Les deux échantillons suivent un ordre déterministe par SHA-256 de `2026-11-27#134/<clé cible>` dans chacun des deux groupes du checkpoint `3744b0e5`. Ils mesurent les preuves d’identité disponibles hors réseau. Le pilote en ligne à cohorte identique et le contrôle des 20 carrières restantes restent nécessaires pour conclure sur le gain HTTP et la couverture. [Checkpoint mesuré](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/3744b0e57089b5683a3629e593b3f909c779bc13/rattrapage_historiques/bilan.json)

### Registre et horaires

`PMU_DATA` présente l’état, le dernier checkpoint, la prochaine échéance théorique, la mesure, la fraîcheur, le motif et la source. `Referentiel_pmu_data` fournit deux vues filtrées, Courses et Chevaux. Une ligne cheval correspond à un ID Geny confirmé, un ID PMU disponible ou, en l’absence d’identifiant, à un contexte stable. Le moteur existant compare les identités et les signatures sportives avec les performances effectivement relues dans Sheets. Les preuves sont issues notamment du mapping de courses, des manifestes, des recherches d’identité, de la résolution par course et des archives de réconciliation déjà consommées par le moteur. Les vues se reconstituent depuis ces sources et sont contrôlées après écriture sous le verrou Sheets.

La référence commune est `Europe/Paris`. Le format de consultation est `JJ/MM/AAAA HH:mm:ss`. Les échanges et preuves gardent un instant avec fuseau. Pour le passage Geny signalé à 14:26, GitHub indique une fin à 13:26:50 Paris et la file durable un dernier contrôle à 13:26:43 Paris. Ces sources concordent. L’écran ou le journal qui a affiché 14:26 n’est pas disponible, donc la cause exacte de cet affichage reste indéterminée. Le contrôle distingue explicitement un horodatage réellement futur d’une conversion normale. [Run Geny](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/actions/runs/45997371859) · [File durable](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/3744b0e57089b5683a3629e593b3f909c779bc13/collecte_incrementale/etat.json)

### Validation et retour arrière

```sh
git fetch origin
git switch --detach origin/fix/127-134-138-autonomie-supervision
python -m unittest discover -s tests -p 'test_*.py'
python -m unittest discover -s dashboard -p 'test_*.py'
```

Les tests de persistance vérifient les écritures concurrentes disjointes, la reprise d’une avance distante et le conflit explicite sur un même fichier. Après intégration, observer deux journées réelles et les créneaux nocturnes. Vérifier le dernier global, les jalons, le rapprochement de chaque réunion, la relecture des deux vues et les KPI Streamlit avant toute clôture. Un revert du code rétablit l’ordonnancement antérieur. Les checkpoints et les onglets déjà alimentés restent consultables. Le workflow 04 fournit l’audit et la sauvegarde vérifiée pour la migration des formats Sheets.
