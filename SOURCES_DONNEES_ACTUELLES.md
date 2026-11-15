# Sources du processus de production

État vérifié dans le code le 15 novembre 2026. La présence d'un collecteur
ne garantit ni la disponibilité de la source ni la complétude de chaque course.
Une absence reste signalée ; aucune valeur n'est fabriquée.

| Source | Données effectivement recherchées | Rôle et limites |
|---|---|---|
| **PMU**, flux public `online.turfinfo.api.pmu.fr` | Programme, date/RnCn/hippodrome, horaires et conditions de course ; partants et non-partants ; âge, sexe, gains, musique, driver/jockey, entraîneur, propriétaire et ferrure du jour ; cotes horodatées ; arrivées officielles ; commentaires et pronostics lorsqu'ils sont publiés. | Référence opérationnelle pour les courses, les partants et les résultats. Le flux public n'est pas une API contractuelle documentée. Les cotes restent informatives et hors des variables ML. |
| **Geny** | Programme et correspondance des courses PMU/Geny ; fiche et identifiant du cheval ; carrière détaillée : dates, hippodromes, discipline, distance, classement/disqualification, chrono et ferrure historique lorsqu'ils sont accessibles. | Source principale des historiques complets, via le collecteur individuel incrémental commun à la production et au rattrapage. Vérification du nombre de performances, de l'identité, des dates et des champs. Respect des refus 403/429 et des délais de reprise. |
| **Equidia** | Avis/commentaires, ordre du pronostic publié, profils des partants (âge, sexe, gains, musique, driver, entraîneur, ferrure selon les champs disponibles), paramètres de course. | Recoupement et complément des données PMU ; association nom/numéro/course contrôlée. Les avis ne sont pas une vérité sportive ni une preuve de performance du modèle. |
| **ZEturf** | Avis/commentaires et pronostic publié ; profils des partants et paramètres de course lorsque le site les expose. | Source secondaire de contexte et de recoupement. Sa numérotation des réunions peut différer : l'hippodrome et la course sont vérifiés. |
| **Open-Meteo** | Prévisions horaires de température, humidité, vent et précipitations ; géocodage si la localisation est univoque. | Captures avant départ seulement, avec URL et horodatage. Une prévision n'est ni une mesure constatée ni l'état officiel de la piste. La précision piste/ville est conservée. |
| **Zone-Turf — données héritées** | Anciennes lignes d'historique et anciens avis déjà enregistrés. | Le cycle actuel ne l'utilise plus comme collecteur principal. Ses identifiants restent distincts des identifiants Geny. Une correspondance vérifiée est nécessaire pour raccorder les anciennes lignes à une carrière Geny. |

**LeTROT** est une source officielle recommandée, mais aucun collecteur LeTROT
n'est actuellement branché dans la chaîne automatique. iTurf et Paris-Turf ne
sont pas des sources automatiques actives non plus. Les rapports d'écuries ne
disposent pas d'un collecteur dédié : seuls les éléments réellement publiés et
capturés ou des observations manuelles sourcées sont utilisables.

## Stockage et traçabilité

Google Sheets sert à consulter et publier les données. La branche GitHub
`pmu-data` conserve les captures validées, états de reprise, versions et preuves
de contrôle. Ces deux supports ne sont pas des fournisseurs de données
hippiques. Les historiques récupérés après une course ne réécrivent jamais les
pronostics ni les instantanés ML gelés avant son départ.

## Identifiants entre sources

`pmu_geny/identites_chevaux_verifiees.json` contient les correspondances
explicitement vérifiées. Pour Jiska de Dream : Zone-Turf **1717076**, Geny
**2724812**. Vérifications : nom et numéro 6 sur la course Geny 1698722
(16 novembre 2026, Nantes, R6C6), puis concordance de deux performances
anciennes (dates, hippodromes, discipline, distance, classement, chrono et
ferrure). La fiche Geny annonce 60 performances, toutes extraites lors de la
vérification locale du 15 novembre à 18:22 UTC.

Le snapshot Sheets conserve désormais la provenance des identifiants. Le
rattrapage migre la cible sans changer le dénominateur de l'inventaire figé.
La publication réutilise les anciennes clés des performances concordantes et
ajoute seulement les lignes manquantes. Les numéros externes sans
correspondance vérifiée sont marqués `IDENTITE_A_VERIFIER` ; ils ne deviennent
jamais automatiquement des URL de cheval Geny. Le contrôle
`IDENTIFIANT_NON_CONCORDANT` reste actif.
