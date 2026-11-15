# Sources du processus de production

État vérifié dans le code le 15 novembre 2026. La présence d'un collecteur
ne garantit ni la disponibilité de la source ni la complétude de chaque course.
Une absence reste signalée ; aucune valeur n'est fabriquée.

| Source | Données effectivement recherchées | Rôle et limites |
|---|---|---|
| **PMU**, flux public `online.turfinfo.api.pmu.fr` | Programme, date/RnCn/hippodrome, horaires et conditions de course ; partants et non-partants ; âge, sexe, gains, musique, driver/jockey, entraîneur, propriétaire et ferrure du jour ; cotes horodatées ; arrivées officielles ; commentaires et pronostics lorsqu'ils sont publiés. | Référence opérationnelle pour les courses, les partants et les résultats. Le flux public n'est pas une API contractuelle documentée. Les cotes restent informatives et hors des variables ML. |
| **Geny** | Programme et correspondance des courses PMU/Geny ; fiche et identifiant du cheval ; carrière détaillée : dates, hippodromes, discipline, distance, classement/disqualification, chrono et ferrure historique lorsqu'ils sont accessibles. | Source principale des historiques complets, via le collecteur individuel incrémental commun à la production et au rattrapage. Vérification du nombre de performances, de l'identité, des dates et des champs. Respect des refus 403/429 et des délais de reprise. |
| **Open-Meteo** | Prévisions horaires de température, humidité, vent et précipitations ; géocodage si la localisation est univoque. | Captures avant départ seulement, avec URL et horodatage. Une prévision n'est ni une mesure constatée ni l'état officiel de la piste. La précision piste/ville est conservée. |
| **Equidia — retirée du cycle actif** | Anciennes captures d'avis et de profils conservées pour traçabilité. | L'audit ci-dessous ne montre pas de commentaire détaillé supplémentaire par rapport à PMU. Aucun nouvel appel automatique ; aucun complément des critères courants ou des nouvelles variables ML. |
| **ZEturf — retirée du cycle actif** | Anciennes captures d'avis conservées pour traçabilité. | Majorité d'étiquettes génériques, pas de gain prédictif démontré et aucun besoin de dépendre d'un compte tiers. Aucun nouvel appel automatique. |
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

## Simplification fondée sur les données

Audit de 87 captures de courses V23 présentes dans `pmu-data` à la révision
`71fe2f5c`, le 15 novembre 2026 :

- Equidia : 1 168 avis non vides, dont 582 étiquettes génériques. Les 586
  commentaires détaillés restants sont tous identiques au commentaire PMU du
  même partant dans la même course : aucun commentaire détaillé supplémentaire.
- ZEturf : 1 035 avis non vides, dont 987 formules génériques relatives au nombre
  de « paramètres réunis ». Ce constat ne prouve aucun gain de pronostic.

PMU est désormais l'unique source des conditions et des critères courants du
cheval, y compris dans les nouvelles captures ML. Aucun ancien complément
Equidia/ZEturf/Zone-Turf n'est utilisé pour combler un champ PMU manquant.
Geny conserve son rôle pour les performances historiques. Open-Meteo est
conservé pour ses données météorologiques distinctes, sans prétendre que leur
présence améliore déjà le TOP3 : cet effet reste à mesurer hors échantillon.

Les anciennes colonnes d'avis tiers sont vidées lors de la publication courante
pour éviter de présenter un avis ancien comme une source encore active.
Les archives et les pronostics gelés ne sont pas réécrits. Les parseurs des
anciens formats restent disponibles pour lire les archives, sans appel réseau
dans la production.

## Identifiants entre sources

`pmu_geny/identites_chevaux_verifiees.json` contient les correspondances
explicitement vérifiées. Pour Jiska de Dream : Zone-Turf **1717076**, Geny
**2724812**. Vérifications : nom et numéro 6 sur la course Geny 1698722
(16 novembre 2026, Nantes, R6C6), puis concordance de deux performances
anciennes (dates, hippodromes, discipline, distance, classement, chrono et
ferrure). La fiche Geny annonce 60 performances, toutes extraites lors de la
vérification locale du 15 novembre à 18:22 UTC.

Le contrôle exhaustif a également identifié 23 anciennes lignes portant le
numéro Zone-Turf avec une URL Geny déjà correcte. La réconciliation couvre
aussi ce format hybride. Le mode de maintenance `reconcilier_identites` du
workflow de rattrapage vérifie chaque doublon sur sa course, sa discipline,
sa distance et son classement, ainsi que la carrière Geny sauvegardée. Il
préserve les champs historiques complémentaires, sauvegarde les lignes
originales sur `pmu-data` avant toute suppression, puis applique un batch
atomique sous le verrou commun et contrôle les clés et les comptages après.

Le snapshot Sheets conserve désormais la provenance des identifiants. Le
rattrapage migre la cible sans changer le dénominateur de l'inventaire figé.
La publication réutilise les anciennes clés des performances concordantes et
ajoute seulement les lignes manquantes. Les numéros externes sans
correspondance vérifiée sont marqués `IDENTITE_A_VERIFIER` ; ils ne deviennent
jamais automatiquement des URL de cheval Geny. Le contrôle
`IDENTIFIANT_NON_CONCORDANT` reste actif.
