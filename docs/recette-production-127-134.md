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
