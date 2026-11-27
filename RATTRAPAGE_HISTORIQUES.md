# Reprise globale des historiques déjà rencontrés

Le workflow **03 — Geny Rattrapage global** (`rattrapage-historiques.yml`)
reprend son état depuis `pmu-data/rattrapage_historiques/etat.json`. Son
inventaire couvre les chevaux déjà rencontrés, toutes dates confondues.

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

Une **actualisation explicite** (`actualiser_inventaire=true` au lancement manuel)
étend le lot aux chevaux déjà rencontrés depuis sa création. Elle archive l'état
précédent, conserve les identités et les preuves de collecte/publication, puis
enregistre une révision avec date, nombre de cibles avant, ajoutées et après.
Les passages programmés gardent ce périmètre figé. Le dénominateur d'une nouvelle
révision doit être distingué de celui des bilans antérieurs.

Une capture préexistante est déjà complète si le classificateur vérifie toutes
les lignes et le total annoncé, si sa date n'est ni absente ni future, si son URL
et son identifiant concordent, et si ses clés de performances sont présentes
dans le registre contrôlé. Un historique complet absent du registre demande
uniquement une synchronisation.

La cohorte « lot de 96 » correspond aux identifiants distincts sans carrière
complète du checkpoint `c0c9471457a8bb8e261e5b01434d85ce77268252`. Le
checkpoint `de5d7660` et la validation de la PR #30 en retrouvaient 58 publiés,
dont un identifiant Zone-Turf réconcilié avec son identifiant Geny. La référence
reste fixe et suit cette correspondance uniquement lorsqu'elle est prouvée dans
l'état de l'inventaire. Les KPI la distinguent du lot global et de ses extensions.

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

Le workflow 03 programme le rattrapage aux minutes 27 et 57, entre 21 h et
07 h en Europe/Paris. Le workflow 02 traite les partants prioritaires aux
minutes 12 et 42 pendant ce créneau. Les deux chaînes partagent le verrou
d’accès Geny et le verrou d’écriture Sheets sérialise les publications.
À chaque passage, le workflow 03 vérifie les obligations PMU et réduit son
budget si nécessaire. Le lancement manuel applique les mêmes gardes métier.

Entre deux chevaux, le rattrapage vérifie si un cycle PMU ou le collecteur courant
attend le verrou. Il termine alors son passage et consolide ses KPI pour céder
la place. Si cette vérification GitHub est indisponible, il cède aussi par prudence.
Un cheval déjà commencé finit sa sauvegarde et sa publication avant de céder.

Le bilan publié dans `rattrapage_historiques/bilan.json` alimente
`PMU_DATA`. L’onglet `Referentiel_pmu_data` détaille les preuves de
correspondance et les historiques effectivement relus dans Sheets.

Les bilans distinguent les tentatives, `captures_validees` et
`collectes_rejetees`, dès les checkpoints intermédiaires. Le motif de fin
indique explicitement une pause de source, une file momentanément épuisée,
une limite de durée ou une priorité de production. Les motifs détaillés du
dernier échec restent consultables, même après résolution. Une collecte réussie
retire son ancien délai d'échec ; une lacune persistante pose son propre délai.
Une ancienne preuve ne dispense pas de recontrôler l'URL, l'identifiant et la
date de la capture. Les revalidations d'archives ont leurs propres compteurs
(`derniere_revalidation`) et ne comptent pas comme de nouvelles consultations.

Un sous-processus déjà commencé peut terminer après le budget ; sa limite reste
240 secondes. Les 403/429 activent la
pause partagée de 30 minutes ; aucun accès n'est contourné. Les autres échecs
conservent un motif et une prochaine tentative après six heures.

Entre 21 h et 7 h Europe/Paris, les cibles déjà engagées dans les courses du jour
et du lendemain passent avant les anciennes carrières sans engagement. Les
partants récents encore incomplets viennent ensuite. Cette priorité nocturne
est partagée avec le collecteur courant ; elle réutilise les index sauvegardés
pour retrouver les contextes de courses. Aucune collecte n'a lieu pendant une
pause Geny active et une publication en attente reste reprise sans recollecte.

**Priorité aux carrières manquantes** : en journée comme la nuit, une carrière
absente ou partielle passe avant une carrière complète à enrichir en ferrures,
y compris si seule cette dernière possède déjà un lien Geny vérifié. La priorité
nocturne des engagements s'applique à l'intérieur de ces catégories. Le collecteur
courant applique aussi ce tri, sans perdre ses limites de production.

À urgence nocturne égale, la reprise termine d'abord les carrières des
identifiants déjà connus, avant de résoudre les seules observations de noms
et courses. Un identifiant sans URL reste un candidat soumis à vérification ;
ce tri ne transforme pas un numéro recensé en preuve d'identité Geny.

Le lecteur de résultats conserve aussi le code source `Tb`, observé dans la
carrière de Louna d'Hucheloup (Rânes, 09/06/2025). Ce code terminal était ignoré,
ce qui rejetait une carrière pourtant extraite sur 38/38 performances. Il est
conservé tel quel, sans rang inventé et sans assouplir les champs obligatoires.

Les diagnostics d'une collecte rejetée peuvent être rejoués depuis leurs
artefacts GitHub (`archives_diagnostics`, jusqu'à cinq IDs séparés par virgules).
Le texte complet reste disponible jusqu'au bloc de qualification, afin de ne
pas tronquer son libellé après une date affichée sur deux lignes. Les captures
ne sont promues que si identité, URL, date originale, total annoncé et champs
redeviennent valides. La date de capture n'est pas remplacée par la date de
revalidation ; l'empreinte de l'archive est conservée. Une carrière déjà valide
est ignorée. La sauvegarde et la publication utilisent les mêmes contrôles et
le même verrou que le reste du rattrapage, sans nouvelle consultation Geny.

Une archive peut aussi retrouver une cible encore sans identifiant Geny si
la demande originale prouve le même nom, la même date/course et le même
numéro, et si la fiche obtenue appartient à la course attendue. Le seul nom
ne suffit pas ; un conflit d'identité empêche toujours la promotion.

Un débutant n'est pas un historique manquant lorsque les données structurées
de la même fiche confirment simultanément zéro performance, une liste vide et
la mention « Inédit », avant son premier départ connu. Sa qualification ne
devient pas une course. La capture porte `INEDIT_AVANT_DEPART` et la preuve
datée ; une ancienne capture à zéro n'est pas rejouée après ce départ pour
prétendre que la carrière est encore vide.

Le bilan expose `phase_reprise`, les `carrieres_distinctes_a_completer`, les
`identifiants_sans_carriere_complete` dédoublonnés et les
`contextes_distincts_sans_identifiant`. Les ferrures sont comptées séparément.
Une capture devenue invalide ne conserve pas une ancienne preuve de complétude.
Une carrière validée et publiée porte une date de complétude ; la production
reprend ensuite ses nouvelles performances au fil des engagements et arrivées.

`TERMINE` exige toutes les cibles complétées, leur synchronisation confirmée et
les KPI `OK`. L'absence de tâche actuellement éligible ne suffit jamais. Les
carrières inaccessibles ou sans lien fiable maintiennent `PARTIEL_REPRENABLE`,
avec motifs et délais. Une capture complète décrit la carrière disponible
à sa date de vérification, pas une carrière définitivement achevée.

Après `TERMINE`, les passages suivants ne relancent aucune collecte.
La notification finale relève de la supervision PMU existante, avec identifiant
de lot, dénominateurs, ajouts confirmés et blocages.

## Pilote de résolution des identités par course

Un créneau nocturne de rattrapage commence par rejouer les preuves locales.
Le pilote fixe ensuite une cohorte de dix courses Geny confirmées couvrant le
plus de places PMU encore sans identifiant. Il ouvre au plus une page de partants
par passage, après les partants prioritaires et sous le verrou habituel. Le
même passage est réservé à cette page. Les lectures individuelles de carrières
reprennent sur les passages suivants et après la fin du pilote.

Chaque lien doit être corroboré par le contexte PMU archivé, le numéro et le nom.
Les conflits restent visibles. Un nom seul ne suffit pas et un lien confirmé
ne valide aucune carrière. Les preuves écrites dans `sources_geny/liens` sont
relues par l'index commun. Les engagements sans rapprochement Geny confirmé
restent dans le bilan. Une nouvelle preuve locale peut les rendre éligibles au
rattrapage ordinaire. Les 403/429 déclenchent la pause commune de trente minutes.
Le pilote permet une seule nouvelle tentative après un tel refus par course.

`rattrapage_historiques/resolution_identites_courses.json` conserve la cohorte,
le nombre de pages lues, les identités confirmées, les conflits, les numéros
sans lien et les exclusions, indépendamment de la publication des historiques.

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

## Inventaire des courses disputées par nom

Le bilan `rattrapage_historiques/courses_passees_par_nom.json` recense les
partants confirmés par le PMU des courses avec une arrivée vérifiée dans le
cache. Le nom est comparé sans tenir compte de la casse. Chaque entrée garde
la graphie d'origine et les numéros et courses observés. Les courses sans
liste de partants vérifiée sont comptées séparément.

Actualiser l'inventaire avec le paramètre `actualiser_inventaire` du workflow
existant pour prendre en charge les nouveaux noms. Une seule cible par nom
est sélectionnée dans cette liste. Les contextes et historiques restent
disponibles pour vérifier les filiations et les homonymes. Une contradiction
entre sources ou deux numéros distincts dans la même course suspendent la
collecte du nom concerné. Les quotas et la priorité aux échéances PMU
s'appliquent à chaque passage.
