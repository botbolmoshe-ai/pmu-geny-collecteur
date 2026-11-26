# Spécifications fonctionnelles PMU–Geny

**Active** signifie reliée à un point d’entrée de service. **Expérimentale** couvre une méthode candidate ou en observation, même affichée. **Non vérifiée** signale un manque de preuve. La révision de référence figure dans les spécifications techniques.

| Règle | Statut | Conditions et paramètres | Source |
| --- | --- | --- | --- |
| F01 Sélection | Active | Trot attelé, monté ou sans sous-type. Discipline de la course, spécialité de réunion en secours si unique. P1 si Vincennes, Groupe I–III ou allocation ≥ 40 000 €. P2 si hippodrome autorisé, ≥ 8 partants et allocation ≥ 12 000 € ou inconnue. Motif explicite sinon. | [niveau](../../pmu_geny/selection_metier_v20_4.py#L80) |
| F02 Identité et participation | Active | Le numéro identifie la ligne de la course. Le lien Geny exige un nom exact unique ou un ID confirmé. Numéros incohérents ou doublons rejettent le relevé Direct. Un NP mémorisé est retiré du classement sauf nouvelle confirmation PMU qu’il est partant. | [liaison](../../pmu_geny/liaison_chevaux_v22.py), [Direct](../../pmu_geny/top3_independants_v22.py#L54) |
| F03 Direct | Active | Calcul avant départ, conservation des versions et d’un relevé compatible plus complet. Départage score décroissant, Crack puis Haut potentiel, numéro croissant. | [Direct](../../pmu_geny/top3_independants_v22.py#L54) |
| F04 Cotes | Active | Collecte et classement de marché indépendants du Direct, avec horodatages distincts de relevé et de rapport. | [cotes](../../pmu_geny/cotes_v19.py) |
| F05 Crack | Active | Trot attelé et identité vérifiée. Gains ≥ 250 000 €, 6 à 10 sorties à statut de disqualification documenté, ≤ 20 % de DAI. Deux podiums Groupe I/II dont une victoire, au moins un podium ≤ 120 jours. | [detecter_crack](../../pmu_geny/profils_partants.py#L102) |
| F06 Haut potentiel | Active | Âge 2–5 ans, ≤ 10 % de DAI sur la même fenêtre. Deux sorties Groupe I–III espacées d’au moins 30 jours entre extrêmes, dernière ≤ 120 jours. Sur les trois dernières sorties toutes ≤ 120 jours, deux podiums dont un proche de la distance cible et une victoire. Progression moyenne ≥ 1 point sur 5 par rapport aux trois précédentes. | [detecter_haut_potentiel](../../pmu_geny/profils_partants.py#L121) |
| F07 IPR | Expérimentale | Indice sur 100 sous IPR_SHADOW_ENABLED, vrai par défaut dans Actions. Contrôle participation, identité Geny, fraîcheur et coupure. J+1 enregistre la préparation sans TOP3. | [IPR](../../pmu_geny/ipr.py), [activation](../../.github/workflows/pmu-v16.yml#L77) |
| F08 ML expérimental | Expérimentale | Modèle entraîné utilisable en service avec statut non calibré, promotion régie par une procédure distincte. | [pointeur](../../pmu_geny/cycle_ml_actif.py#L20), [prédiction](../../pmu_geny/ml_v19.py#L548) |
| F09 Même mode de départ | Expérimentale | Mélange de 90 % du Direct et 10 % de forme dans le même mode de départ, classement candidat archivé séparément. | [candidat départ](../../pmu_geny/top3_independants_v22.py) |
| F10 Résultats et matching | Active | Intersection de trois numéros de la sélection pré-départ avec le podium officiel, contrôle des preuves et de leurs horodatages. | [matching_pct](../../pmu_geny/sync_google_sheets.py#L312), [rapprochement](../../pmu_geny/rapprochement_reunions.py) |

## Coefficients du Direct

Barème des places 1 à 5, 5 / 3,5 / 2,5 / 1,5 / 1. Le moteur contextuel pèse Geny à 70 % dès trois sorties exploitables ou 45 % en dessous, et utilise la source seule si l’autre manque. Les sorties historiques doivent dater de 1 à 365 jours avant la course cible et appartenir à la même discipline lorsque celle-ci est connue. Le calcul lisse la moyenne par un poids de 1,5 à la note 2 et borne le score à 0–5.

Le poids par sortie multiplie distance, hippodrome, ferrure, niveau et temps. Distance ≤ 100 / 250 / 500 m puis au-delà, 1 / 0,85 / 0,55 / 0,25, inconnue 0,75. Hippodrome identique / différent / inconnu, 1 / 0,70 / 0,80. Ferrure, 1 / 0,65 / 0,85. Niveau par rapport d’allocation cible/historique, 0,70 au-delà de 2, 0,85 au-delà de 1,35, 1 sinon ou si insuffisamment documenté. Temps jusqu’à 30 / 90 / 180 / 365 jours, 1 / 0,85 / 0,65 / 0,40. Le contexte documenté exige trois sorties, deux proches et deux comparaisons de ferrure si ferrure courante connue. [Moteur contextuel](../../pmu_geny/formes_contextuelles_v32.py#L63)

**Non vérifiée pour le replay**. Le Direct principal ne transmet pas l’heure d’observation au calcul historique de base. La date de la sortie est vérifiée, mais la disponibilité effective de l’historique au moment d’un replay reste à vérifier. [Calcul historique](../../pmu_geny/formes_contextuelles_v32.py#L95)

## Coefficients de l’IPR

Mérite relatif (effectif − rang)/(effectif − 1) avec effectif de 2 à 40 et rang admissible. Sinon barème ordinal / 5. DAI vaut zéro. Au plus dix sorties de 1 à 365 jours, avant le jour local d’observation, même discipline, distance documentée à ±500 m maximum. Dates ambiguës écartées. Poids = distance × niveau × exp(−âge/180), multiplié en cas de divergence documentée par 0,85 pour hippodrome, 0,8 piste, 0,8 mode, 0,85 ferrure. Score = 100 × moyenne pondérée des mérites. Confiance élevée si taille effective ≥ 5, couverture ≥ 0,67, DAI pondérés ≤ 0,20. Moyenne si ≥ 3, ≥ 0,33 et ≤ 0,40. Faible sinon. Enregistrement plafonné à 30 min depuis le relevé et un jour local avant course. [evaluer_cheval](../../pmu_geny/ipr.py#L35), [enregistrer](../../pmu_geny/ipr.py#L176)

La musique PMU retient au plus cinq jetons reconnus, élimine le marqueur d’année et filtre les jetons d’une autre discipline lorsque la discipline cible est connue. La moyenne est normalisée avec les poids max(0,4, 1 − 0,12 × i) sur les sorties retenues. Trois chevaux notés sont nécessaires pour calculer un TOP3. Un TOP3 peut être partiel si l’effectif ou une partie seulement des scores est documentée. [Parsing](../../pmu_geny/top3_independants_v22.py#L16), [forme PMU](../../pmu_geny/formes_contextuelles_v32.py#L39)

## Variables du modèle expérimental actif

La couverture est celle du pointeur archivé. Un zéro indique une variable déclarée sans valeur numérique disponible pour cet entraînement.

| Variable | Valeurs numériques d’entraînement |
| --- | ---: |
| `courses_30j` | 207 |
| `courses_60j` | 207 |
| `courses_120j` | 207 |
| `podiums_30j` | 150 |
| `podiums_120j` | 189 |
| `victoires_120j` | 207 |
| `disqualifications_120j` | 207 |
| `score_forme` | 189 |
| `forme_30j` | 150 |
| `forme_ancien` | 167 |
| `jours_repos` | 199 |
| `distance_m` | 2876 |
| `distance_ecart_m` | 199 |
| `aptitude_hippodrome` | 0 |
| `taux_podium_distance` | 193 |
| `nb_partants` | 1554 |
| `meteo_pluie_mm` | 486 |
| `meteo_vent_kmh` | 486 |
| `meteo_temperature_c` | 486 |
| `meteo_humidite_pct` | 486 |
| `avis_experts_score` | 0 |
| `info_ecurie_score` | 0 |
| `driver_score` | 255 |
| `entraineur_score` | 161 |
| `pmu_score_direct` | 2787 |
| `age_ans` | 2622 |
| `gains_euros` | 2622 |
| `sexe_male` | 2622 |
| `sexe_femelle` | 2622 |
| `sexe_hongre` | 2622 |
| `ferrure_d4` | 1554 |
| `ferrure_dp` | 1554 |
| `ferrure_da` | 1554 |
| `ferrure_p4` | 1554 |
| `ferrure_pa` | 1554 |
| `ferrure_pp` | 1554 |
| `discipline_montee` | 1554 |
| `forme_pmu_discipline` | 1468 |
| `forme_geny_comparable` | 160 |
| `forme_ferrure_neutre` | 138 |
| `forme_ferrure_moderee` | 138 |
| `forme_ferrure_actuelle` | 138 |
| `chrono_comparable_mediane_sec_km` | 27 |
| `chrono_comparable_nb_sorties` | 27 |
| `tandem_podium_lisse` | 0 |
| `tandem_courses` | 0 |
| `avis_pmu_structure` | 0 |
| `position_autostart_absolue` | 300 |
| `depart_autostart` | 397 |
| `distance_autostart` | 397 |
| `position_autostart_relative` | 120 |
| `ligne_autostart` | 120 |
| `forme_geny_meme_depart` | 23 |
| `sorties_geny_meme_depart` | 23 |
| `recul_depart_m` | 926 |
| `est_crack` | 72 |
| `est_haut_potentiel` | 72 |
| `sorties_geny_comparables_120j` | 65 |
| `ferrures_historiques_comparees` | 50 |

[Déclarations](../../pmu_geny/ml_v19.py#L15), [pointeur archivé](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/b1cf91b5c94e214e8e6cb2c09dc4edd98fa9f1ad/ml/modele_experimental_actif.json)
