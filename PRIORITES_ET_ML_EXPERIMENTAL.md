# Priorités de collecte et apprentissage actif

Le cycle principal continue de préparer les courses et les premières prévisions.
Le worker incrémental ne consulte désormais que les chevaux dont un engagement
PMU est encore à venir aujourd'hui ou demain, par heure de départ croissante.
Un cheval identifié dans plusieurs engagements est traité pour le plus proche.
Les non-partants sont exclus ; les anciennes files et captures sont conservées.
Le contrôle 403/429, les délais de réessai, les validations d'identité et les
checkpoints restent inchangés. Les publications en attente sont reprises sans
nouvelle requête Geny, y compris pour une course passée.

La reprise du stock est limitée à un cheval par passage, au plus une fois par
heure (cron UTC :45, budget par défaut deux minutes). Elle cède aux traitements
prioritaires et reste différée tant que les programmes ou profils PMU sont
absents/anciens, qu'un historique futur est à compléter, qu'une publication est
en attente ou que les prévisions du jour doivent être actualisées après une
nouvelle capture. Ce contrôle précède même l'ouverture d'une session Sheets.
Le bilan indique la raison du report ; aucun succès technique n'est présenté
comme une fin de rattrapage.

L'API Python `inc.run` conserve sa compatibilité avec les anciens appelants ;
les points d'entrée de production CLI appliquent la politique des prochains
départs. Le rattrapage utilise toujours le même moteur, sous sa condition de
préparation et son quota réduit.

## ML : apprentissage et mesure dès les données disponibles

Chaque cycle principal lance une expérience sur les instantanés **réellement
enregistrés avant départ** et leurs arrivées admissibles, sans attendre le seuil
de promotion de 100 courses / 700 lignes. Une empreinte des données évite de
recalculer la même expérience sans changement.

Les jours train, validation et test sont sélectionnés selon la disponibilité
temporelle des étiquettes, jamais selon le résultat du test. Il faut au minimum
trois périodes chronologiques exploitables et les deux classes pour entraîner.
Les anciens instantanés ne sont ni reconstruits ni enrichis après les résultats.

`ml/cycle_experimental.json` contient le statut, les effectifs et la synthèse.
`ml/experiences/automatique-EMPREINTE/` conserve le modèle expérimental, le rapport,
les scores du test et les empreintes des sources. Les résultats restent marqués
`EXPERIMENTAL_NON_CALIBRE_NON_DEPLOYE`, sans probabilités fiables ni promotion.
Le moteur de production conserve ses seuils, son contrôle de comparaison hors
échantillon et son cycle après 20 h Paris. Une expérience n'écrase jamais le
modèle déployé ni les prévisions live.

Vérification locale sur copie de production : 78 courses / 1 052 lignes
admissibles ; 53 courses train, 23 validation, 2 test. Ce dernier effectif est
insuffisant pour conclure à une amélioration fiable. Les résultats définitifs
de chaque passage sont ceux du rapport horodaté conservé dans pmu-data.
