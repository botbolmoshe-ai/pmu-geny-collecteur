# Collecte des historiques : intégration du pilote à la production

## Processus

Le pilote `test/boucle-historiques-courus` (c08feed) a enregistré 163 historiques
validés et synchronisés. Son principe est repris : un cheval, un processus neuf,
validation, sauvegarde distante, Sheets, puis le suivant. Le clic sur le nom exact
et la conservation du code source `Dpg` sont repris du pilote.

Le cycle PMU prépare les données et les correspondances de courses. Il ne lance
plus l'ancien collecteur d'historiques par lots. Le workflow
`historiques-incrementaux.yml` traite une file permanente à la demi-heure,
24h/24, par passages de 15 minutes (20 au maximum en lancement manuel).
Les deux workflows partagent `pmu-donnees-production`, sans annulation concurrente.
Le calcul TOP3/ML reste réservé au jour J entre 07h00 et 21h00 Paris et avant départ.

## Dates et actualisation

`pmu-data/collecte_incrementale/etat.json` conserve par cheval :

- `historique_complet_au_utc` : heure réelle de la capture Geny validée ;
- `derniere_performance_date` : date de la dernière performance effectivement extraite ;
- `derniere_course_officielle_utc` : départ de la dernière course dont une arrivée est enregistrée ;
- `derniere_verification_utc` et `prochaine_verification_utc` pour les nouvelles captures ;
- motif d'actualisation, statut de collecte, de synchronisation, erreurs et délai de reprise.

Une ancienne capture est datée à partir de son `extrait_utc`, jamais à partir de
la migration, du commit Git ou de la date de modification du fichier. Une capture
sans date vérifiable reste à vérifier. La colonne existante
« Historique · Mise à jour UTC » continue d'afficher la date disponible ; aucune
colonne ni feuille supplémentaire n'est créée par la synchronisation individuelle.

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
restent non résolus. La sélection diurne et la pause partagée après 403/429 restent
inchangées ; la nuit n'autorise aucun accès pendant cette pause.

## Reprise et intégrité

La file, les historiques et le journal de production sont sauvegardés sur
`pmu-data` avant Sheets. Une erreur de push arrête le passage ; aucune poursuite
avec une sauvegarde distante non confirmée. Une erreur Sheets ne recollecte pas
Geny : seule la synchronisation est reprise. Les ajouts sont idempotents et les
écritures individuelles dans les lignes de courses se limitent aux métadonnées
de disponibilité de l'historique. Les sélections et les formules de référence en
colonne E des KPI sont préservées.

Les refus 403/429 imposent une pause globale de 30 minutes, partagée avec le cycle
PMU. Les autres échecs sont retentables après six heures. Les consultations de
chevaux sont espacées d'au moins 30 secondes. Une exécution de sous-processus
est bornée à 240 secondes. Il n'y a plus de plafond métier de six fiches : la
durée du passage et les règles d'accès bornent la progression.

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
