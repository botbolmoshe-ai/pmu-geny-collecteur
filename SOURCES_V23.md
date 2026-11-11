# Sources de course et d'avis V23

Sources actives : PMU, Equidia et ZEturf. Geny conserve son rôle pour les historiques.
Zone-Turf n'est plus interrogé par le cycle automatique ; les anciens parseurs restent
uniquement pour lire les archives et tester leur compatibilité.

- PMU : paramètres du programme, partants et pronostic éditorial publié par l'API.
- Equidia : paramètres, profils, avis d'entraîneurs, interviews et classement éditorial
  explicitement publié. Les notes Equidia ne sont pas converties en probabilités.
- ZEturf : conditions, profils, commentaires par cheval et sélection publiée.

Date, hippodrome et titre sont contrôlés avant tout rapprochement. Un ancien titre
entre parenthèses est accepté si le titre principal correspond exactement. Les
numéros de réunion peuvent différer ; chaque cheval est ensuite rapproché par son
nom entier normalisé et son numéro dans cette course, jamais par son numéro seul.

Les lacunes de profil PMU sont complétées par Equidia puis ZEturf ; les contradictions
sont tracées, sans écraser une valeur PMU connue. Chaque profil conserve sa provenance.
Les commentaires et les pronostics sont affichés distinctement par source dans
l'onglet existant Courses & Prévisions. Aucune création d'onglet supplémentaire.
Les colonnes héritées Geny/Zone-Turf sont vidées avant leur réaffectation ; les
archives JSON d'origine restent conservées.

Toutes les captures sont horodatées avant le départ. Une page ou une erreur est mise
en cache une heure pour limiter les requêtes. Les accès refusés restent signalés et
ne sont pas contournés. Une donnée absente ne devient jamais un avis neutre. Un ancien
relevé peut être conservé avec sa date et l'échec du dernier contrôle. La couverture
et la disponibilité des pronostics sont distinctes. Les textes identiques entre
sources sont signalés, sans compter artificiellement plusieurs avis indépendants.

Ce changement enrichit les données et leur présentation. Il ne modifie pas les
coefficients des modèles ni les sélections déjà figées. La couverture éditoriale
varie selon la course et l'heure de publication ; trois sites interrogés ne signifient
pas trois pronostics toujours disponibles.

Validation : régression hors ligne (103 tests, dont 2 archives optionnelles), et
collectes réelles avant départ du 12 novembre 2026 à Vincennes R1C1 et Amiens R4C1.
