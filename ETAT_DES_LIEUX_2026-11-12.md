# Audit de la chaîne PMU — 12 novembre 2026

## Diagnostic

Le processus sait collecter des données réelles, conserver son état, calculer un classement simple, récupérer des arrivées et alimenter Google Sheets. Il constitue une base de travail exploitable. Sa qualité prédictive n'est pas démontrée et plusieurs défauts faussent les indicateurs ou fragiliseraient la mise en service du ML.

**Priorité : fiabiliser les données, les classements et leur mesure avant de complexifier le modèle ou d'élargir la collecte.**

Audit du code `main` au commit `2c854d56c515cc7d1c1e091e70522e55806d323e` et des données `pmu-data` au commit `05556ec3a8a37e7be6d94b72944ff5ec6b4cd7af`, sauvegardées à 19 h 46 UTC. Références GitHub actualisées sans changement constaté. Lecture du Google Sheets réel et du journal GitHub du dernier cycle ; aucune écriture distante. Les chiffres de performance ci-dessous concernent exclusivement les **13 courses du 12 novembre** retenues par le filtre actuel, à Vincennes et Amiens. Le registre contient également 10 courses du lendemain : ses 23 courses et 318 participations ne constituent donc pas un échantillon de 23 courses terminées.

## Contrôle étape par étape

| Étape | État constaté | Conséquence |
|---|---|---|
| Programme PMU | 13 courses retenues le 12 novembre ; 183 déclarations reçues, effectifs conformes aux nombres déclarés | Couverture complète du périmètre retenu, pas de tout le trot français |
| Profils du jour | Driver, entraîneur, âge, sexe, gains et ferrure alimentent le registre ; la ferrure reste incomplète pour certains partants | Couverture à suivre champ par champ, sans inventer les valeurs absentes |
| Sources éditoriales | Pronostic publié PMU : 13/13 courses ; Equidia : 13/13 ; ZEturf : 10/13 | Sources disponibles, mais disponibilité ne signifie ni indépendance des avis ni efficacité prédictive |
| Météo | 13 contextes avec prévision horodatée avant départ ; valeurs visibles sur les 183 lignes du jour | La collecte fonctionne dans l'état actuel ; des erreurs anciennes restent affichées dans l'orchestration |
| Manifestes Geny | 4/13 courses du jour avec manifeste | Le parcours dépendant de Geny reste très incomplet |
| Historiques associés aux partants | 17/183 participations du jour ; toutes dans R1C1 | La qualité des fichiers disponibles ne compense pas leur faible couverture des partants |
| TOP3 direct | 13/13 classements avec horodatage avant départ | Calcul opérationnel, mais parseur de musique défectueux et horizons variables |
| TOP3 historique | 1/13 sélection figée ; R1C1 : 2, 8, 12 | Fonctionne sur un cas complet, pas encore sur la majorité des courses |
| Instantanés ML | 13/13 captures avant départ | Le figement trop précoce empêche d'incorporer les enrichissements reçus ensuite |
| Modèle ML | Aucun modèle entraîné ; 18 courses / 254 lignes admissibles au total, y compris des courses antérieures | Seuils de démarrage de 100 courses / 700 lignes non atteints |
| Arrivées PMU | 13/13 fichiers récupérés | Lecture des classements opérationnelle ; caractère définitif et corrections officielles à mieux contrôler |
| Évaluations et audits | 13 bilans directs dans Sheets ; 1 fichier d'évaluation historique et 4 audits anciens formats | Plusieurs circuits de mesure coexistent et ne couvrent pas les mêmes méthodes |
| Synchronisation Sheets | 318 lignes courses et 13 bilans retrouvés ; clés uniques sur les plages lues ; concordance des champs contrôlés avec la source locale | Transport opérationnel ; indicateurs du quatrième onglet erronés |

Les 49 fichiers d'historique disponibles comprennent **46 complets et 3 partiels**. « Complet » signifie conforme au nombre annoncé lors de l'extraction, pas nécessairement à jour à chaque nouvelle participation. Les trois partiels sont les identifiants 2905469, 2907579 et 2907581. Le registre actuel et futur ne rattache un historique qu'à **28 participations sur 318, soit 8,8 %**. Ces dénominateurs diffèrent de ceux du seul 12 novembre.

## Résultats réellement observés

Pour les 13 TOP3 directs horodatés avant le départ :

| Chevaux retrouvés dans le podium | Nombre de courses |
|---|---:|
| 0 sur 3 | 6 |
| 1 sur 3 | 4 |
| 2 sur 3 | 3 |
| 3 sur 3 | 0 |

Soit **10 chevaux retrouvés au total**, **0,77 par course**, **3/13 courses avec au moins deux chevaux retrouvés (23,1 %)** et **aucun 3 sur 3**. Ces résultats décrivent une seule journée avec un moteur dont le parseur est imparfait. Ils n'estiment ni une probabilité future ni une rentabilité.

Le repère théorique d'une sélection uniforme de trois chevaux parmi les concurrents non retirés serait d'environ 0,67 cheval du podium par course sur ces effectifs. Ce repère n'est pas une stratégie exécutée et le faible écart observé ne démontre aucun avantage statistique. Une comparaison aux favoris au même instant reste impossible faute de cotes enregistrées.

Sur Vincennes R1C1, le TOP3 historique figé à 11 h 47 UTC a sélectionné **2, 8, 12**, contre une arrivée **2, 1, 13** : **1/3**. Le TOP3 direct **10, 8, 12** donne **0/3**. Le recalcul des exports et du bilan sur une copie temporaire reproduit ces résultats sans refaire les prédictions. Le tableau de bord visible met surtout en avant le direct et ne permet pas une lecture complète des quatre référentiels prévus.

## Corrections prioritaires

### P0 — Lecture de la musique et traitement des non-partants

**Défaut confirmé du parseur de musique.** Dans `pmu_geny/top3_independants_v22.py`, la même suite de performances produit des résultats différents selon les espaces : `1a2a3a` ne conserve que `1a` et donne 5 points, alors que `1a 2a 3a` donne 9,98 points. `DaDa1a` ne produit aucune observation. Les chiffres du changement d'année `(25)` sont interprétés comme des places. Une lecture publique du schéma PMU confirme l'utilisation réelle de musiques compactes et de marqueurs d'année. Cette requête après course a uniquement servi à contrôler l'extracteur ; elle n'a alimenté aucune prévision ni mesure rétrospective.

**Action :** un parseur qui reconnaît chaque performance, ignore les années et conserve la discipline ; tests sur des chaînes réelles, disqualifications, positions à deux chiffres et changements d'année. Versionner le moteur corrigé et commencer une nouvelle série de prévisions. Les anciens résultats restent ceux du moteur initial.

**Défauts confirmés du traitement des NP.** Une simulation isolée montre qu'un cheval déclaré non-partant 31 minutes auparavant peut revenir dans le TOP3 historique : son exclusion est conditionnée à un contrôle de moins de 30 minutes. Dans le direct, une autre simulation confirme qu'un nouveau retrait peut laisser subsister le cheval dans le TOP3 : la mise à jour est refusée parce que le nombre de chevaux observés diminue. Le code assimile ce retrait légitime à une perte d'information et conserve l'ancien relevé.

Le cas réel Amiens R4C3 conserve une sélection directe **4, 5, 8** calculée dès la veille, alors que le dernier état PMU identifie le **5 non-partant**. Les fichiers disponibles ne permettent pas de dater sa première déclaration NP avec précision ; les deux défauts de code, eux, sont reproduits indépendamment.

**Action :** conserver l'exclusion d'un NP confirmé tant qu'une modification officielle explicite n'est pas enregistrée ; traiter séparément fraîcheur du contrôle, qualité des observations et évolution du nombre de concurrents. Un retrait confirmé doit toujours déclencher une nouvelle version valide, même si la liste devient plus courte. Tester également les dates futures et les contrôles incomplets.

### P0 — Réparer la mesure dans Sheets

L'onglet `Data Quality & KPI` affiche **0 arrivée et 0 évaluation**, alors que les 13 bilans se trouvent aux lignes 2 à 14 de `Résultats & Analyse`. Les formules des arrivées et de performance commencent à **N15, O15, P15 et H15** : elles sautent tous ces bilans. Les scores des bilans sont par ailleurs écrits comme chaînes ; leur compatibilité avec `ISNUMBER` doit être corrigée et contrôlée.

Le même onglet affiche **189 partants avec historique disponible**, contre **28 comptes strictement positifs** dans les lignes lues. Sa formule compte les cellules correspondant à `?*`, pas les valeurs numériques supérieures à zéro. Les compteurs de ferrure présentent aussi un écart entre le nombre de valeurs affiché et les statuts d'absence : réconcilier ces indicateurs à partir des mêmes lignes.

L'audit Python annonce zéro TOP3 historique car il compte `baseline_top3`, champ non propagé par la transformation `source_rows`. Pourtant le fichier R1C1 est présent et évaluable. Il faut distinguer absence de prédiction et absence de champ d'export.

**Action :** produire les métriques de référence depuis une table canonique par course et méthode ; utiliser des nombres natifs pour les scores ; réconcilier automatiquement cette table, les fichiers et Sheets. Séparer les courses terminées des préparations J+1. N'afficher « meilleure méthode » que si une comparaison est possible ; « Direct (0/3) » seul n'est pas une victoire comparative.

### P1 — Récupérer les cotes au bon endroit

**Aucune cote non nulle dans les fichiers des 183 déclarations du jour.** Les extracteurs cherchent `rapportDirect`, `coteDirect`, `cote` ou `rapportProbable`. Le schéma PMU réellement consulté expose notamment `dernierRapportDirect.rapport`, avec `typePari`, `typeRapport` et `dateRapport`. Le champ observé sur un exemple contient bien une valeur, mais le code actuel ne le lit pas.

**Action :** ajouter un extracteur validé de ce schéma, contrôler le type de pari, le numéro du cheval et la date du rapport, conserver l'heure d'observation et celle de publication. Ne jamais utiliser une lecture après course comme cote connue avant départ. Les cotes restent exclues des variables prédictives et servent seulement de comparaison. Regrouper les deux extracteurs actuellement dupliqués pour éviter une nouvelle divergence.

### P1 — Stabiliser les instantanés et le futur ML

Les **18 courses admissibles proviennent d'instantanés V22.0** ; dix autres instantanés V22.1 existent mais concernent le lendemain, sans arrivée. Dans les 254 lignes étiquetées, la météo, l'âge, les gains, le sexe, les indicateurs de ferrure et l'aptitude à l'hippodrome sont tous absents. Le score de forme manque sur **238/254 lignes**. Les profils et la météo visibles aujourd'hui dans Sheets ne prouvent donc pas leur présence dans les données d'entraînement figées.

La première capture PMU, parfois faite dès J-1, rend le fichier immuable ; les historiques ou la météo obtenus ensuite ne l'enrichissent plus. Inversement, il ne faut pas remplir les anciennes captures avec des connaissances ultérieures.

Le calcul des caractéristiques diffère aussi entre apprentissage et prédiction : `snapshot_pmu` apporte musique et profils actuels, tandis que `predict` appelle `features` sans cet enrichissement. Le ML en production resterait en outre dépendant d'un manifeste Geny : l'orchestrateur quitte le parcours avant `predict` quand le manifeste manque, même si la capture PMU est indépendante.

**Action :** une seule construction de caractéristiques utilisée à l'entraînement et en production ; plusieurs captures immuables et horodatées, par exemple préparation J-1, référence H-1 et dernière mise à jour avant départ ; un schéma versionné et des contrôles de couverture. Tester l'égalité des caractéristiques entre les deux parcours pour les mêmes données et le même instant.

Le seuil de 100 courses ne garantit pas la qualité du modèle. Avant promotion, comparer sur les mêmes courses un classement de forme, le direct corrigé et le ML, avec validation chronologique, métriques TOP3 et calibration séparée. La procédure actuelle choisit automatiquement le meilleur de deux modèles au Brier, sans exiger qu'il batte une référence. Distinguer attelé et monté : le moteur actuel applique les mêmes règles aux deux spécialités.

### P1 — Rendre les heures et versions comparables

Les 13 derniers classements directs sont tous antérieurs au départ, mais l'avance varie d'environ **2 minutes à plus de 21 heures**. Le fichier direct est remplacé à chaque mise à jour, et la comparaison utilise cette dernière version. Les instantanés ML et la baseline historique ne suivent pas toujours le même horizon.

**Action :** référence commune H-1, puis versions pré-départ supplémentaires conservées. Comparer les méthodes sur la même course et au même instant. Enregistrer aussi les profils pré-départ : les 13 fichiers `partants_actuels` du jour ont été remplacés par une lecture après départ, ce qui limite la reconstitution exacte des contrôles de l'époque. Les captures ML restent, elles, horodatées avant départ dans les cas contrôlés.

Le déclenchement d'entraînement exige actuellement 20 h 00–20 h 14 heure Paris. Le dernier cycle a démarré vers 20 h 44 : une exécution horaire retardée peut manquer entièrement cette fenêtre. Préférer « un entraînement quotidien si éligible et non encore effectué », avec statut daté et décision explicite.

### P1 — Sécuriser les résultats et réunifier les bilans

Le lecteur d'arrivée exige trois rangs cohérents, mais ne contrôle pas explicitement un statut officiel définitif. Si un fichier existe déjà, il refuse toute révision : une correction ultérieure ne serait pas intégrée. Le module d'audit historique dépend d'un manifeste et ignore les TOP3 directs ; ses quatre fichiers du jour ne couvrent donc pas les treize bilans directs.

**Action :** distinguer résultat provisoire et définitif, garder leurs versions et recalculer les évaluations dérivées après une correction officielle. Un seul évaluateur doit couvrir direct, historique initial, historique après NP, ML et marché, avec contrôle de l'antériorité de chaque prévision.

### P2 — Améliorer le rendement de la collecte et la supervision

- Le stock d'historiques est limité et peu rattaché aux courses suivies. Prioriser un périmètre réalisable, notamment Vincennes attelé, puis mesurer la couverture avant de l'élargir. Un maximum de six fiches nouvelles par cycle ne garantit pas six nouvelles fiches utiles : la consommation du quota est actuellement déduite du quota attribué, pas d'un compteur exact de requêtes réussies.
- Les historiques marqués complets sont réutilisés sans règle d'expiration fondée sur les nouvelles courses du cheval. Introduire une actualisation incrémentale et conserver les versions déjà utilisées dans les prédictions.
- Les refus Geny 429 sont effectivement rencontrés ; conserver le respect du cooldown et des accès. Planifier les reprises selon l'urgence et la valeur des données manquantes, sans augmenter aveuglément la fréquence.
- Le filtre du 13 novembre exclut sept courses de Toulouse parce que `toulouse la cepiere` ne correspond pas à l'entrée `toulouse` de la liste P2. Décider le périmètre voulu et maintenir une table d'alias vérifiés. Le suivi actuel n'est pas exhaustif de tout le trot français ni des courses après 19 h.
- Les erreurs anciennes restent dans l'orchestration alors que certaines données ont depuis été collectées, notamment la météo. Séparer dernier essai, dernier succès, ancien incident résolu et absence actuelle ; éviter les listes d'alertes cumulées sans clôture.
- Les installations et plusieurs appels sont redondants : paquet ML réinstallé à chaque cycle, deux relevés de cotes pour certaines courses, construction des données Sheets répétée. Réutiliser les réponses pendant un cycle, mutualiser les lectures par hippodrome et mesurer durée, requêtes et ajouts utiles avant optimisation.
- Le bridge Sheets lit seulement `A1:BS5000`. Au-delà de 5 000 lignes, il pourrait ne plus reconnaître des clés et les réajouter. Lire des bornes calculées et surveiller doublons et cellules devenues obsolètes ; ne jamais nettoyer les archives sans migration définie.

## Ordre de réalisation recommandé

1. **Lot A — Confiance minimale :** musique, NP, KPI et nombres natifs ; tests des cas réels et réconciliation fichiers → Sheets. Objectif : aucun NP connu sélectionné, même lecture de la musique avec ou sans espaces, 13 arrivées et 13 évaluations correctement comptées sur cette référence.
2. **Lot B — Expérience mesurable :** cotes sourcées, versions H-1 et finales, profils pré-départ, résultats définitifs et évaluateur commun. Objectif : comparer honnêtement les méthodes sur les mêmes courses.
3. **Lot C — Données utiles au modèle :** couverture des historiques, schéma de caractéristiques unique, captures successives, fraîcheur et séparation attelé/monté. Objectif : constituer un vrai échantillon d'apprentissage avant tout entraînement de production.
4. **Lot D — Coût et exploitation :** appels mutualisés, quotas exacts, reprises contrôlées, entraînement quotidien idempotent et indicateurs de santé fonctionnelle. Objectif : réduire le coût par course complète, plutôt que le seul nombre d'exécutions.

## Preuves et limites

- Les **104 tests hors ligne réussissent**. Les reproductions du parseur et du NP montrent néanmoins que la suite ne couvre pas suffisamment ces comportements métier.
- Le cycle GitHub [43293169966](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/actions/runs/43293169966) est réussi ; son journal confirme 318 lignes source Courses, 1 023 lignes source Historique et 13 lignes source Résultats. La lecture du Sheets confirme les clés et les champs contrôlés des participations et bilans ; elle ne valide pas exhaustivement toutes les anciennes lignes d'historique.
- La lecture PMU publique utilisée pour contrôler le schéma est postérieure aux courses et conservée séparément. Aucune cote rétrospective ni nouvelle prévision n'en a été déduite.
- Les codes et données ont été audités sans modifier le moteur en production, les branches distantes ou le Google Sheets. La disponibilité actuelle de toutes les pages Geny/Equidia/ZEturf n'a pas été retestée par une collecte massive ; les statuts cités proviennent des captures existantes.
- Reproduction locale : `.venv/bin/python resultats/reprise/audit_chaine.py`. Données détaillées : `resultats/reprise/audit_chaine.json` ; couverture par course : `resultats/reprise/couverture_courses.csv` ; tests : `resultats/reprise/tests_audit.log` ; lectures Sheets et formules : `resultats/reprise/sheets_*.json`.

Principaux fichiers examinés : `auto_v18.py`, `top3_independants_v22.py`, `pronostics_v18.py`, `ml_v19.py`, `resultats_v18.py`, `audit_predictif_v20_1.py`, `sync_google_sheets.py`, `qualite_registre_v21.py`, `traitement_course.py`, `liaison_chevaux_v22.py`, les sources V23 et le workflow `.github/workflows/pmu-v16.yml`.
