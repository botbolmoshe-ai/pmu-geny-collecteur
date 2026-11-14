# Reprise globale des historiques déjà rencontrés

Le workflow `rattrapage-historiques.yml` dispose de son propre déclenchement et
de son état `pmu-data/rattrapage_historiques/etat.json`. Il ne dépend d'aucun
nouvel engagement et n'utilise aucune fenêtre de sept jours. Son code est
développé sur `feature/reprise-historiques-globale`, puis déployé sur `main`.

## Périmètre et inventaire

Au premier passage, le moteur lit intégralement « Historique chevaux » et
« Courses & Prévisions ». Le contrôle indépendant des clés vérifie l'intégrité
avant toute collecte. Cet inventaire est rapproché de tous les journaux, captures,
manifestes, exports et partants PMU sauvegardés, toutes dates confondues,
non-partants inclus.

Les identifiants Geny connus sont dédoublonnés. Un nom non identifié conserve
son contexte de course ; des homonymes ne sont pas fusionnés arbitrairement.
Le bilan compte donc des **cibles d'inventaire**, pas un nombre supposé de chevaux
uniques tant que toutes les identités ne sont pas résolues. Les provenances et
contextes restent dans l'état. Un conflit de nom pour un même identifiant reste
à vérifier. Aucun identifiant de cheval n'est inventé. Pour un identifiant déjà
observé sans URL, le chemin canonique `/cheval/<id>` est seulement un candidat,
traité après les liens déjà prouvés : HTTP 200, URL finale portant le même ID et
nom de cheval présent doivent être réellement vérifiés avant l'extraction.
Le diagnostic de cette vérification est conservé ; un échec n'est pas une identité
acceptée et les refus d'accès conservent la pause partagée.

Les clés de courses Sheets `date|hippodrome|RnCn` sont rapprochées du format PMU
`date_RnCn`. Une observation déjà inventoriée n'est jamais supprimée : si nom,
date, course et numéro concordent, elle est reliée à sa cible équivalente. Seule
la cible principale déclenche une collecte et sa preuve est partagée après
validation. Deux courses différentes ne sont pas fusionnées sur le seul nom.
Le bilan distingue les cibles conservées et les travaux distincts restants.

L'inventaire du lot est figé : les passages suivants ne perdent pas les anciennes
cibles et n'ajoutent pas automatiquement les nouveaux engagements. Ces derniers
continuent d'être traités par la production. Les correspondances d'anciennes
courses peuvent être retrouvées hors réseau depuis les index Geny sauvegardés,
en réutilisant les règles de rapprochement existantes. Les cibles non résolues
restent explicites et bénéficient des preuves apparues aux passages suivants.

Une capture préexistante est déjà complète si le classificateur vérifie toutes
les lignes et le total annoncé, si sa date n'est ni absente ni future, si son URL
et son identifiant concordent, et si ses clés de performances sont présentes
dans le registre contrôlé. Un historique complet absent du registre demande
uniquement une synchronisation.

## Un moteur et des sauvegardes indépendantes

Le rattrapage réutilise `historiques_incrementaux.run(mode='rattrapage')`,
le sous-processus individuel, le validateur et `SynchroniseurSheets`.
Il n'y a pas de deuxième collecteur ni de deuxième synchroniseur HTTP.

Chaque cheval est collecté, validé, sauvegardé sur `pmu-data`, puis synchronisé.
Le rattrapage publie uniquement l'historique et consolide les KPI en fin de passage.
Il n'écrit pas les lignes de prévisions ou de résultats, ni les instantanés ML.
Son checkpoint ne remplace jamais `collecte_incrementale/etat.json`.
Les captures et le journal d'identité restent partagés pour que la production
bénéficie des historiques complétés. Les anciennes captures sont archivées.

Une interruption après collecte reprend la publication. Une erreur des KPI
reprend les seuls KPI. Les contrôles de croissance, d'ajout de clés, de lecture
complète et de relecture après écriture sont ceux de la production.

## Planification et limites

Le workflow est proposé aux minutes 15 et 45 de chaque heure, avec un budget de
collecte de dix minutes par passage. Il partage `pmu-donnees-production`, sans
interruption d'un traitement actif. Il est autonome dans son déclenchement et sa
file, mais ses accès aux données partagées sont sérialisés avec la production.
GitHub peut retarder les horaires et remplacer un passage en attente par un
autre : la file persistante garantit sa reprise à un passage ultérieur, pas une
heure d'exécution exacte ni une priorité absolue de production.

Entre deux chevaux, le rattrapage vérifie si un cycle PMU ou le collecteur courant
attend le verrou. Il termine alors son passage et consolide ses KPI pour céder
la place. Si cette vérification GitHub est indisponible, il cède aussi par prudence.
Un cheval déjà commencé finit sa sauvegarde et sa publication avant de céder.

Un sous-processus déjà commencé peut terminer après le budget ; sa limite reste
240 secondes. Les chevaux sont espacés de 30 secondes. Les 403/429 activent la
pause partagée de 30 minutes ; aucun accès n'est contourné. Les autres échecs
conservent un motif et une prochaine tentative après six heures.

`TERMINE` exige toutes les cibles complétées, leur synchronisation confirmée et
les KPI `OK`. L'absence de tâche actuellement éligible ne suffit jamais. Les
carrières inaccessibles ou sans lien fiable maintiennent `PARTIEL_REPRENABLE`,
avec motifs et délais. Une capture complète décrit la carrière disponible
à sa date de vérification, pas une carrière définitivement achevée.

Après `TERMINE`, les passages suivants ne relancent aucune collecte.
La notification finale relève de la supervision PMU existante, avec identifiant
de lot, dénominateurs, ajouts confirmés et blocages.

## Exploitation

Lancement manuel : « PMU - Rattrapage global des historiques », `max_minutes`
entre 1 et 15. Les diagnostics et l'état sont archivés 30 jours dans Actions ;
l'état durable reste dans `pmu-data`.

Le résumé compact `rattrapage_historiques/bilan.json` est sauvegardé dans le même
commit que l'état complet. Il permet à la supervision de lire la progression et
la dernière écriture contrôlée sans charger toute la file.

Un inventaire local sans réseau nécessite le snapshot Sheets déjà contrôlé :

```bash
python -m pmu_geny.rattrapage_historiques --cache cache_pmu
python -m unittest discover -s tests -p 'test_v30*offline.py' -v
```

Les tests techniques ne mesurent pas une amélioration des pronostics : celle-ci
se vérifie sur les sélections figées avant départ et les arrivées officielles.
