# Collecte des historiques : intégration du pilote à la production

## Processus

Le pilote `test/boucle-historiques-courus` (c08feed) a enregistré 163 historiques
validés et synchronisés. Son principe est repris : un cheval, un processus neuf,
validation, sauvegarde distante, Sheets, puis le suivant. Le clic sur le nom exact
et la conservation du code source `Dpg` sont repris du pilote.

Le workflow `historiques-incrementaux.yml` prévoit un passage aux minutes 12
et 42 entre 21 h et 7 h, et aux minutes 05, 20, 35 et 50 entre 7 h et 21 h,
heure de Paris. L'heure réelle de début détermine le mode si GitHub retarde un
passage. La nuit, la file des partants à venir passe avant le rattrapage du stock.
Le passage manuel garde sa durée configurable (20 minutes au maximum).

Le jour, le workflow **02 — Geny Collecte incrémentale** sauvegarde d’abord
les captures dans sa file durable. Un job distinct reprend cette file pour la
publication Sheets sous le verrou commun. La nuit, le workflow 02 donne la
priorité aux engagements J/J+1 et cède si une obligation PMU doit être traitée.
Le workflow 03 exécute le rattrapage global sur son propre créneau nocturne.

Le cycle global PMU est dû toutes les heures en journée. Les jalons H-3 et H-2,
les arrivées et les acquisitions J/J+1 gardent leurs preuves propres. Le secours
réévalue les tâches dues et le relais Geny vérifie qu’aucun passage n’est déjà
en file avant un déclenchement.

Comparer la couverture du même jour dans la file incrémentale, les preuves
des jalons H-3/H-2 et les publications effectivement relues dans Sheets.
`PMU_DATA` présente les acquisitions et publications par chaîne.
`Referentiel_pmu_data` restitue les preuves de correspondance et l’état
des carrières.

## Dates et actualisation

`pmu-data/collecte_incrementale/etat.json` conserve par cheval :

- `historique_complet_au_utc` : heure réelle de la capture Geny validée ;
- `derniere_performance_date` : date de la dernière performance effectivement extraite ;
- `derniere_course_officielle_utc` : départ de la dernière course dont une arrivée est enregistrée ;
- `derniere_verification_utc` et `prochaine_verification_utc` pour les nouvelles captures ;
- motif d'actualisation, statut de collecte, de synchronisation, erreurs et délai de reprise.

Une ancienne capture est datée à partir de son `extrait_utc`, jamais à partir de
la migration, du commit Git ou de la date de modification du fichier. Une capture
sans date vérifiable reste à vérifier. La consultation affiche la date disponible dans la projection Paris, au format
`JJ/MM/AAAA HH:mm:ss`. L’instant original reste dans la preuve technique.

Un cheval engagé est revérifié après 24 heures, ou après une nouvelle course
officielle. Le rattrapage des courses des sept derniers jours reste possible.
Une fois la dernière course passée effectivement couverte, l'absence de nouvel
engagement évite une consultation quotidienne inutile. Une arrivée non encore
publiée dans la carrière Geny reste `PUBLICATION_GENY_EN_ATTENTE`, retentable
après six heures ; une simple consultation réussie ne prouve pas cette couverture.

Entre 21 h et 7 h, heure de Paris, les partants sans historique complet daté sont
prioritaires : engagements du jour et du lendemain, puis partants récents encore
incomplets, puis simples actualisations. Les liens de courses peuvent être
retrouvés depuis l'index Geny déjà sauvegardé, avec le même rapprochement prudent
que le rattrapage global et sans nouvelle requête au programme. Les liens ambigus
restent non résolus. La pause partagée après 403/429 s'applique également de nuit.

## Reprise et intégrité

La file, les historiques et le journal de production sont sauvegardés sur
`pmu-data` avant Sheets. Une erreur de push arrête le passage ; aucune poursuite
avec une sauvegarde distante non confirmée. Une erreur Sheets ne recollecte pas
Geny : seule la synchronisation est reprise. Les ajouts sont idempotents et les
écritures individuelles dans les lignes de courses se limitent aux métadonnées
de disponibilité de l'historique. Les sélections et les formules de référence en
colonne E des KPI sont préservées.

Les refus 403/429 imposent une suspension globale d'au moins 30 minutes, prolongée
si l'en-tête `Retry-After` l'exige. Le journal partagé impose 30 secondes entre
deux chevaux, ou 60 secondes après un refus jusqu'à dix validations consécutives.
La sauvegarde et la publication consomment ce délai. Une attente longue reporte
l'accès et libère le verrou. Le sous-processus de collecte est borné à 240 secondes.
Les bilans enregistrent les requêtes HTTP Geny, les refus, les délais et les
carrières validées et publiées par heure de passage.

Un historique partiel ou dont des performances ont disparu ne remplace pas le
complet existant. Les captures remplacées sont archivées sous
`historiques_versions/<id>/`. Une différence de contenu inexpliquée reste à
contrôler, même si le site annonce le même nombre de courses.

Les manifestes de courses sont reconstruits sans réseau lorsque toutes les
identités nécessaires sont connues. Les noms ambigus et les liens non résolus
restent explicites. Les fichiers de prévisions, instantanés ML et résultats
n'appartiennent pas au périmètre des checkpoints du worker.

## Validation et exploitation

```bash
python -m unittest discover -s tests -p 'test_*offline.py' -q
python -m pmu_geny.historiques_incrementaux --cache reference_pmu
```

La seconde commande produit uniquement l'inventaire local, sans réseau ni Sheets.
Pour publier, utiliser le workflow dédié ; les identifiants Google déjà configurés
dans les secrets Actions sont requis et ne sont jamais affichés.

Le test réel du 13 novembre a révélé un suffixe du lecteur vidéo
`00:00 | / | 00:00` après un classement `Dai`. Ce suffixe exact est ignoré pour
lire le rang et comparer les versions ; aucune valeur de classement n'est devinée.
Une seconde extraction réelle de Nimagine a validé 15 performances sur 15,
identité confirmée. Les diagnostics sont dans le rapport de validation et les
artefacts d'exécution, pas dans le code métier.

Les tests techniques ne démontrent pas un gain prédictif. Celui-ci doit être
mesuré séparément sur les pronostics pré-départ enregistrés.
