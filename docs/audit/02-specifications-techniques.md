# Spécifications techniques PMU–Geny

## Flux et points d’entrée

PMU fournit programme, participants, cotes et arrivées. Geny fournit identification, carrière et preuves de contexte. Le cycle produit Direct, Cotes, ML et IPR dans le cache. Les workflows restaurent et persistent les données sur pmu-data. Sheets projette le registre, puis les certificats de jalons sont contrôlés et persistés. Streamlit lit le registre. L’apprentissage et l’évaluation prospective exploitent les instantanés et arrivées. [Cycle](../../pmu_geny/cycle_production.py), [traitement](../../pmu_geny/traitement_course.py), [persistance](../../pmu_geny/persistance_production.py)

| Workflow | Déclenchement et rôle |
| --- | --- |
| [pmu-v16.yml](../../.github/workflows/pmu-v16.yml) | Cron à :07/:22/:37/:52, manuel et secours. Planifie, traite les jalons et arrivées dues, persiste avant Sheets, certifie la publication puis persiste de nouveau. Compléments Geny après publication, KPI et relais historiques sous conditions. |
| [historiques-incrementaux.yml](../../.github/workflows/historiques-incrementaux.yml) | Crons 00–06 et 21–23 à :12/:42, 07–20 à :05/:20/:35/:50. Budget et pause vérifiés avant chargement du navigateur. Possibilité de déclencher le PMU dû, puis collecte/sauvegarde/synchronisation par cheval. |
| [rattrapage-historiques.yml](../../.github/workflows/rattrapage-historiques.yml) | Validation du budget et du lot, inventaire, reprise globale et archivage. |
| [migration-structure-geny.yml](../../.github/workflows/migration-structure-geny.yml) | Inventaire, sauvegarde chiffrée et application manuelle conditionnelle avec relecture. |
| [validation-iterative-v21.yml](../../.github/workflows/validation-iterative-v21.yml) | Compile, lance les tests et la recette 48 h, vérifie registre et paliers. Job conditionnel de migration des dates. |
| [dashboard-validation.yml](../../.github/workflows/dashboard-validation.yml) | Tests indépendants du dashboard. |

Verrou partagé pmu-donnees-production pour les principaux chemins d’écriture. Créneaux H-3 et H-2 calculés depuis le premier départ de réunion, anticipation 55 min, fraîcheur 30 min. H-1 reste lisible pour les archives. Global dû après une heure depuis la dernière publication, hors plage nocturne. Priorité JALONS → RAPPROCHEMENT → PRÉPARATION → GLOBAL. Le rattrapage conserve huit minutes avant l’obligation PMU. [planifier](../../pmu_geny/echeances_production.py#L121), [executer](../../pmu_geny/cycle_production.py#L9)

Le parseur Geny combine texte et lignes DOM, reconnaît dates, classements, disqualifications et distances, et archive un diagnostic d’accès. Cadence persistante 30 s, 60 s en reprise, dix validations pour sortir de la reprise, timeout 240 s et réserve de checkpoint 60 s. Les 403/429 déclenchent une pause ou une cadence réduite selon l’état. [collecte](../../pmu_geny/collecte_geny_v4.py#L113), [cadence](../../pmu_geny/cadence_geny.py), [reprise](../../pmu_geny/historiques_incrementaux.py)

## ML

Les chemins snapshot_pmu et dataset capturent les variables avant départ et joignent les résultats vérifiés. Le candidat actif exploite les variables ACTIVE_FEATURES, ajoute des indicateurs d’imputation et utilise la régression logistique par défaut ou le gradient boosting selon le rapport expérimental. L’empreinte évite le réentraînement lorsque les entrées sont inchangées. Le chargement contrôle le SHA-256. Le cycle de promotion est éligible après 20 h Paris, sauf mode forcé, et applique volumes, complétude, validation temporelle et seuil prospectif dont la borne basse de l’IC bootstrap 95 % doit être positive. [variables](../../pmu_geny/ml_v19.py#L15), [candidat actif](../../pmu_geny/cycle_ml_actif.py), [cycle](../../pmu_geny/cycle_ml.py), [seuils](../../pmu_geny/maturite_ml.py)

## Google Sheets et Streamlit

Synchronisation par colonnes canoniques, rapprochement des clés historiques, plan d’écriture et publication via moteur central. Fenêtre du registre des courses à partir du 12 novembre 2026. Les KPI sont calculés en Python. La migration de dates traite les valeurs et formats natifs et prévoit une relecture. Streamlit utilise un scope Sheets en lecture seule et présente Accueil, Courses, Résultats, Performance, Historique et Qualité. Filtres de date, hippodrome et profils, fiches cheval et vue de couverture Geny selon l’écran. [sync](../../pmu_geny/sync_google_sheets.py#L1174), [KPI](../../pmu_geny/kpi_registre.py), [dates](../../pmu_geny/dates_registre.py), [interface](../../dashboard/app.py)

### Paramètres ML et chronologie

Seuils par défaut de préproduction, 150 courses, 1 500 observations, 30 prospectives et 80 % de complétude. Pour la production, 300 courses, 3 000 observations, 100 prospectives et 90 %. Régression logistique pondérée (2 000 itérations maximales, standardisation), ou HistGradientBoosting (120 itérations, 9 feuilles maximum, régularisation L2 de 2). Graine 42. Imputation constante à −1 et indicateurs sur le chemin de service expérimental. Les deux crons d’historiques déclarent Europe/Paris. Le cron du workflow principal ne déclare pas de fuseau. [Seuils](../../pmu_geny/maturite_ml.py), [modèles](../../pmu_geny/experience_ml.py#L107), [cron](../../.github/workflows/historiques-incrementaux.yml#L3)

## Révisions et périmètre

- [Code main](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/tree/a4e868477423f5d15dfb332d14ee31da5cd3369b)
- [Partition de données pmu-data](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/tree/b1cf91b5c94e214e8e6cb2c09dc4edd98fa9f1ad)

## Configurations et dépendances versionnées

- [.devcontainer/devcontainer.json](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/.devcontainer/devcontainer.json)
- [.github/workflows/dashboard-validation.yml](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/.github/workflows/dashboard-validation.yml)
- [.github/workflows/historiques-incrementaux.yml](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/.github/workflows/historiques-incrementaux.yml)
- [.github/workflows/migration-structure-geny.yml](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/.github/workflows/migration-structure-geny.yml)
- [.github/workflows/pmu-v16.yml](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/.github/workflows/pmu-v16.yml)
- [.github/workflows/rattrapage-historiques.yml](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/.github/workflows/rattrapage-historiques.yml)
- [.github/workflows/validation-iterative-v21.yml](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/.github/workflows/validation-iterative-v21.yml)
- [.gitignore](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/.gitignore)
- [.streamlit/config.toml](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/.streamlit/config.toml)
- [archive/github-actions-v20/test-codes-geny.yml](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/archive/github-actions-v20/test-codes-geny.yml)
- [archive/github-actions-v20/test-fiche-historique-unique.yml](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/archive/github-actions-v20/test-fiche-historique-unique.yml)
- [archive/github-actions-v20/test-historique-isole.yml](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/archive/github-actions-v20/test-historique-isole.yml)
- [archive/github-actions-v20/test-historique-progressif.yml](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/archive/github-actions-v20/test-historique-progressif.yml)
- [archive/github-actions-v20/test-rapprochement-isole.yml](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/archive/github-actions-v20/test-rapprochement-isole.yml)
- [archive/github-actions-v20/test-reste-historique.yml](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/archive/github-actions-v20/test-reste-historique.yml)
- [archive/github-actions-v20/test-suite-historique.yml](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/archive/github-actions-v20/test-suite-historique.yml)
- [archive/github-actions-v21/audit-generique-integre.yml](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/archive/github-actions-v21/audit-generique-integre.yml)
- [archive/github-actions-v21/reprise-historiques-v21.yml](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/archive/github-actions-v21/reprise-historiques-v21.yml)
- [archive/github-actions-v21/verification-v21.yml](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/archive/github-actions-v21/verification-v21.yml)
- [dashboard/requirements.txt](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/dashboard/requirements.txt)
- [dashboard/secrets.example.toml](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/dashboard/secrets.example.toml)
- [pilotage/declencher-production-v21.txt](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pilotage/declencher-production-v21.txt)
- [pmu_geny/identites_chevaux_verifiees.json](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/identites_chevaux_verifiees.json)
- [pmu_geny/rattrapage_lot_96.json](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/rattrapage_lot_96.json)
- [requirements-ml.txt](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/requirements-ml.txt)
- [requirements.txt](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/requirements.txt)

## Inventaire par module et symbole

Les signatures et issues de contrôle sont extraites de l’AST. Les imports sont relevés statiquement. Cette annexe donne un index d’inspection et ne prouve pas la portée dynamique d’un appel.

### [dashboard/app.py](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/dashboard/app.py)

Imports déclarés · collections, datetime, google.oauth2.service_account, googleapiclient.discovery, hmac, pandas, plotly.express, re, streamlit, trot_analytics.dates, trot_analytics.logic, trot_analytics.observations, trot_analytics.performance, trot_analytics.profils, trot_analytics.quality, trot_analytics.usages, zoneinfo
- [read_registry](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/dashboard/app.py#L27) · paramètres aucun
- [read_geny_history](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/dashboard/app.py#L42) · paramètres aucun
- [render_geny](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/dashboard/app.py#L72) · paramètres page
- [badges](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/dashboard/app.py#L179) · paramètres libelles
- [profils_ligne](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/dashboard/app.py#L187) · paramètres row
- [fmt](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/dashboard/app.py#L218) · paramètres value, unit

### [dashboard/test_app.py](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/dashboard/test_app.py)

Imports déclarés · datetime, importlib.util, pathlib, streamlit, streamlit.testing.v1, trot_analytics, trot_analytics.observations, trot_analytics.quality_dates, trot_analytics.usages, types, unittest, unittest.mock, zoneinfo
- [setUp](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/dashboard/test_app.py#L14) · paramètres self
- [source](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/dashboard/test_app.py#L30) · paramètres self, history=True, odds=False, market_top3=False, dual_profile=False, ipr=False
- [table](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/dashboard/test_app.py#L76) · paramètres rows
- [test_authentication_blocks_reads_until_login](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/dashboard/test_app.py#L84) · paramètres self
- [test_navigation_date_filters_and_optional_history](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/dashboard/test_app.py#L90) · paramètres self
- [test_geny_history_and_quality](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/dashboard/test_app.py#L113) · paramètres self
- [batch](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/dashboard/test_app.py#L130) · paramètres **kwargs
- [test_profils_de_course_dans_le_tableau_et_styles](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/dashboard/test_app.py#L152) · paramètres self
- [test_ipr_est_lu_du_registre_et_affiche_en_italique](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/dashboard/test_app.py#L178) · paramètres self
- [test_ipr_affiche_en_police_normale_apres_promotion](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/dashboard/test_app.py#L193) · paramètres self
- [test_cumul_filtre_et_fiche_cheval](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/dashboard/test_app.py#L203) · paramètres self
- [test_cote_horodatee_visible_sans_selection_de_marche](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/dashboard/test_app.py#L221) · paramètres self
- [test_courses_charge_le_top3_cotes_meme_si_un_ancien_module_est_en_memoire](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/dashboard/test_app.py#L231) · paramètres self
- [test_performance_real_page_and_filters](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/dashboard/test_app.py#L247) · paramètres self

### [dashboard/test_dates_registre.py](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/dashboard/test_dates_registre.py)

Imports déclarés · dashboard.trot_analytics.dates, datetime, pmu_geny.dates_registre, pmu_geny.migration_dates_sheets, unittest
- [test_instants_paris](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/dashboard/test_dates_registre.py#L9) · paramètres self
- [test_dates_natives_et_vides](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/dashboard/test_dates_registre.py#L23) · paramètres self
- [test_url_et_texte_source](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/dashboard/test_dates_registre.py#L32) · paramètres self
- [test_plan_ne_touche_pas_aux_clefs_formules_et_indices](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/dashboard/test_dates_registre.py#L40) · paramètres self
- [text](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/dashboard/test_dates_registre.py#L43) · paramètres value
- [test_publication_et_reprise_mixte](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/dashboard/test_dates_registre.py#L61) · paramètres self
- [test_rejouer_le_format_cible_sans_alterer_le_style_ni_la_valeur](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/dashboard/test_dates_registre.py#L78) · paramètres self

### [dashboard/test_logic.py](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/dashboard/test_logic.py)

Imports déclarés · datetime, trot_analytics.logic, unittest
Point d’entrée __main__ déclaré.
- [test_matching](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/dashboard/test_logic.py#L5) · paramètres self
- [test_selection](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/dashboard/test_logic.py#L7) · paramètres self
- [test_records](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/dashboard/test_logic.py#L12) · paramètres self
- [test_couverture_utilise_le_premier_depart_de_la_reunion](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/dashboard/test_logic.py#L14) · paramètres self
- [test_result](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/dashboard/test_logic.py#L28) · paramètres self

### [dashboard/test_performance.py](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/dashboard/test_performance.py)

Imports déclarés · datetime, trot_analytics.performance, unittest
- [row](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/dashboard/test_performance.py#L9) · paramètres self, key='a', day='2026-11-17', direct=66.67, ml=0
- [test_zero_is_valid_not_missing](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/dashboard/test_performance.py#L20) · paramètres self
- [test_common_perimeter_and_missing](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/dashboard/test_performance.py#L26) · paramètres self
- [test_duplicate_keys_and_invalid_chronology](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/dashboard/test_performance.py#L32) · paramètres self
- [test_bad_published_matching](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/dashboard/test_performance.py#L36) · paramètres self
- [test_stale_status_allows_direct_but_keeps_ml_gate](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/dashboard/test_performance.py#L39) · paramètres self
- [test_cumulative_is_weighted_by_courses](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/dashboard/test_performance.py#L47) · paramètres self

### [dashboard/test_quality.py](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/dashboard/test_quality.py)

Imports déclarés · copy, trot_analytics.quality, unittest
Point d’entrée __main__ déclaré.
- [test_source_total_zero_and_missing_remain_distinct](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/dashboard/test_quality.py#L7) · paramètres self
- [test_percent_value_keeps_its_original_reference_total](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/dashboard/test_quality.py#L18) · paramètres self
- [test_maturite_rates_have_a_dedicated_section](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/dashboard/test_quality.py#L24) · paramètres self
- [test_geny_identity_indicators_keep_their_own_counts](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/dashboard/test_quality.py#L31) · paramètres self
- [test_sections_and_search_include_descriptions](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/dashboard/test_quality.py#L45) · paramètres self
- [test_text_timestamps_and_decimals_are_display_values](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/dashboard/test_quality.py#L53) · paramètres self

### [dashboard/test_quality_dates.py](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/dashboard/test_quality_dates.py)

Imports déclarés · datetime, trot_analytics.quality_dates, unittest
- [row](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/dashboard/test_quality_dates.py#L7) · paramètres self, day, n=1, hist=0, np='PARTANT'
- [test_ferrure_legacy_et_son_statut_source_sont_lus](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/dashboard/test_quality_dates.py#L12) · paramètres self
- [test_focus_date_et_intervalle_avec_denoms_et_np](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/dashboard/test_quality_dates.py#L20) · paramètres self
- [test_cotes_sans_releve_et_non_partants_exclus](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/dashboard/test_quality_dates.py#L30) · paramètres self
- [test_aucune_donnee_ne_devient_un_taux_zero](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/dashboard/test_quality_dates.py#L41) · paramètres self
- [test_releves_historiques_ne_reutilisent_pas_la_valeur_actuelle](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/dashboard/test_quality_dates.py#L46) · paramètres self
- [test_date_future_de_course_admise_mais_date_invalide_ignoree](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/dashboard/test_quality_dates.py#L59) · paramètres self

### [dashboard/trot_analytics/__init__.py](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/dashboard/trot_analytics/__init__.py)

Imports déclarés · aucun

### [dashboard/trot_analytics/dates.py](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/dashboard/trot_analytics/dates.py)

Imports déclarés · datetime, re, zoneinfo
- [date_kind](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/dashboard/trot_analytics/dates.py#L15) · paramètres field · retours littéraux DATE, DATE_TIME
- [instant_iso](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/dashboard/trot_analytics/dates.py#L23) · paramètres value
- [vers_nombre](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/dashboard/trot_analytics/dates.py#L31) · paramètres field, value
- [depuis_nombre](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/dashboard/trot_analytics/dates.py#L45) · paramètres field, value
- [vers_cellule_operationnelle](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/dashboard/trot_analytics/dates.py#L63) · paramètres field, value · retours littéraux
- [afficher_date](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/dashboard/trot_analytics/dates.py#L73) · paramètres value
- [afficher_instant](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/dashboard/trot_analytics/dates.py#L78) · paramètres value, zone=PARIS
- [meme_date_sheets](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/dashboard/trot_analytics/dates.py#L83) · paramètres field, left, right
- [lire_date](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/dashboard/trot_analytics/dates.py#L98) · paramètres value
- [lire_instant_consultation](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/dashboard/trot_analytics/dates.py#L109) · paramètres value, zone
- [nombre_paris](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/dashboard/trot_analytics/dates.py#L124) · paramètres value, *, utc=True
- [afficher_source](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/dashboard/trot_analytics/dates.py#L132) · paramètres value · Projeter uniquement les segments datés de la provenance publiée.
- [afficher_segment](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/dashboard/trot_analytics/dates.py#L144) · paramètres match
- [indicateur_horodate](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/dashboard/trot_analytics/dates.py#L154) · paramètres label
- [afficher_valeur_kpi](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/dashboard/trot_analytics/dates.py#L158) · paramètres label, value

### [dashboard/trot_analytics/logic.py](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/dashboard/trot_analytics/logic.py)

Imports déclarés · dates, datetime, math
- [number](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/dashboard/trot_analytics/logic.py#L6) · paramètres value
- [timestamp](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/dashboard/trot_analytics/logic.py#L12) · paramètres value
- [matching](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/dashboard/trot_analytics/logic.py#L15) · paramètres value
- [records](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/dashboard/trot_analytics/logic.py#L19) · paramètres values
- [selected](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/dashboard/trot_analytics/logic.py#L25) · paramètres rows, method
- [podium](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/dashboard/trot_analytics/logic.py#L39) · paramètres value
- [result_matching](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/dashboard/trot_analytics/logic.py#L45) · paramètres row, method, now=None · Use recorded scores, validate the visible evidence; no new prediction.
- [couverture_reunions](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/dashboard/trot_analytics/logic.py#L73) · paramètres groups, now

### [dashboard/trot_analytics/observations.py](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/dashboard/trot_analytics/observations.py)

Imports déclarés · dates, html, usages
- [tableau_observations](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/dashboard/trot_analytics/observations.py#L8) · paramètres rows, groupe · retours littéraux
- [order](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/dashboard/trot_analytics/observations.py#L17) · paramètres row
- [display](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/dashboard/trot_analytics/observations.py#L22) · paramètres row, field
- [text](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/dashboard/trot_analytics/observations.py#L30) · paramètres value, italic
- [tableau_geny](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/dashboard/trot_analytics/observations.py#L49) · paramètres rows, context, groupe
- [cell](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/dashboard/trot_analytics/observations.py#L52) · paramètres tag, value, italic

### [dashboard/trot_analytics/performance.py](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/dashboard/trot_analytics/performance.py)

Imports déclarés · collections, dates, datetime, logic, pandas, plotly.express, streamlit
- [performance_rows](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/dashboard/trot_analytics/performance.py#L10) · paramètres results, now · One row per unambiguous course with a published, verified score.
- [summarize](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/dashboard/trot_analytics/performance.py#L33) · paramètres rows
- [evolution](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/dashboard/trot_analytics/performance.py#L45) · paramètres rows
- [render_performance](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/dashboard/trot_analytics/performance.py#L64) · paramètres results, now

### [dashboard/trot_analytics/profils.py](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/dashboard/trot_analytics/profils.py)

Imports déclarés · aucun
- [libelles_profils](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/dashboard/trot_analytics/profils.py#L17) · paramètres value · Normaliser l'ancien libellé du registre à la lecture.

### [dashboard/trot_analytics/quality.py](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/dashboard/trot_analytics/quality.py)

Imports déclarés · collections, dates, datetime, logic, pandas, plotly.express, quality_dates, streamlit, zoneinfo
- [display_value](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/dashboard/trot_analytics/quality.py#L11) · paramètres value, *, rate=False · retours littéraux —
- [is_rate](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/dashboard/trot_analytics/quality.py#L24) · paramètres label
- [quality_sections](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/dashboard/trot_analytics/quality.py#L28) · paramètres kpis, query='' · Keep the source denominator; no ratio or total is inferred by the UI.
- [render_quality](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/dashboard/trot_analytics/quality.py#L64) · paramètres kpis, courses=None, history=None

### [dashboard/trot_analytics/quality_dates.py](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/dashboard/trot_analytics/quality_dates.py)

Imports déclarés · collections, datetime, logic, statistics, zoneinfo
- [day](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/dashboard/trot_analytics/quality_dates.py#L14) · paramètres value
- [date_rows](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/dashboard/trot_analytics/quality_dates.py#L19) · paramètres rows, field, start, end
- [cohort_metrics](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/dashboard/trot_analytics/quality_dates.py#L24) · paramètres courses, start, end, now=None · retours littéraux
- [add](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/dashboard/trot_analytics/quality_dates.py#L32) · paramètres d, label, value, total, definition
- [ferrure](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/dashboard/trot_analytics/quality_dates.py#L47) · paramètres row · retours littéraux
- [daily_series](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/dashboard/trot_analytics/quality_dates.py#L104) · paramètres courses, start, end
- [history_series](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/dashboard/trot_analytics/quality_dates.py#L109) · paramètres history, start, end, as_of=None
- [latest_history](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/dashboard/trot_analytics/quality_dates.py#L124) · paramètres rows

### [dashboard/trot_analytics/usages.py](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/dashboard/trot_analytics/usages.py)

Imports déclarés · dataclasses
- [en_observation](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/dashboard/trot_analytics/usages.py#L8) · paramètres usage
- [italique](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/dashboard/trot_analytics/usages.py#L18) · paramètres self

### [pmu_geny/__init__.py](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/__init__.py)

Imports déclarés · aucun

### [pmu_geny/audit_checkpoint.py](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/audit_checkpoint.py)

Imports déclarés · argparse, datetime, json, pathlib
Point d’entrée __main__ déclaré.
- [age_horodatage](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/audit_checkpoint.py#L12) · paramètres valeur, maintenant
- [analyser](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/audit_checkpoint.py#L22) · paramètres bilan, maintenant=None, seuil_heures=6
- [entier](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/audit_checkpoint.py#L26) · paramètres cle
- [main](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/audit_checkpoint.py#L93) · paramètres aucun

### [pmu_geny/audit_dates_sheets.py](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/audit_dates_sheets.py)

Imports déclarés · collections, dashboard.trot_analytics.dates, datetime, json, lectures_sheets, moteur_sheets, os, pathlib, sync_google_sheets, sys
Point d’entrée __main__ déclaré.
- [categorie](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/audit_dates_sheets.py#L14) · paramètres cell · retours littéraux ISO instant, URL et instant, formule, nombre, texte
- [pages](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/audit_dates_sheets.py#L40) · paramètres engine, tab, props
- [inventorier](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/audit_dates_sheets.py#L61) · paramètres engine

### [pmu_geny/audit_generique_hors_ligne.py](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/audit_generique_hors_ligne.py)

Imports déclarés · __future__, argparse, collections, controle_historique, datetime, json, pathlib
Point d’entrée __main__ déclaré.
- [main](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/audit_generique_hors_ligne.py#L13) · paramètres aucun

### [pmu_geny/audit_predictif_v20_1.py](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/audit_predictif_v20_1.py)

Imports déclarés · __future__, cotes_v19, csv, datetime, ml_v19, pathlib
- [analyser_course](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/audit_predictif_v20_1.py#L15) · paramètres cache, course, manifest · retours littéraux ARRIVEE_NON_VERIFIEE, AUDIT_ENREGISTRE, DEPART_INVALIDE
- [ranking](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/audit_predictif_v20_1.py#L37) · paramètres doc
- [summarize](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/audit_predictif_v20_1.py#L40) · paramètres ranks
- [bilan_global](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/audit_predictif_v20_1.py#L82) · paramètres cache · Résumé descriptif uniquement, aucune ré-optimisation automatique. · retours littéraux AUCUN_AUDIT

### [pmu_geny/auto_v18.py](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/auto_v18.py)

Imports déclarés · __future__, argparse, audit_predictif_v20_1, contexte_meteo_v20, cotes_v19, datetime, echeances_production, export_v17, historiques_incrementaux, ipr, json, maturite_ml, ml_v19, os, partants_actuels_v21, pathlib, planification_v20_2, pronostics_v18, rapprochement_v20_6, re, resultats_v18, selection_metier_v20_4, sources_experts_v23, sys, top3_independants_v22, unicodedata, urllib.error, urllib.parse, urllib.request, zoneinfo
Point d’entrée __main__ déclaré.
- [save](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/auto_v18.py#L20) · paramètres path, doc
- [load](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/auto_v18.py#L24) · paramètres path, default=None
- [get_json](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/auto_v18.py#L28) · paramètres url, timeout=16
- [_list](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/auto_v18.py#L39) · paramètres doc, *names
- [_num](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/auto_v18.py#L46) · paramètres doc, *fields
- [_str](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/auto_v18.py#L54) · paramètres doc, *fields · retours littéraux
- [_country_code](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/auto_v18.py#L60) · paramètres reunion · Inspecter les emplacements connus, sans déduire la France d'un nom. · retours littéraux
- [programme_diagnostic](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/auto_v18.py#L76) · paramètres doc, date · Retourne les courses et les compteurs exacts des exclusions PMU.
- [exclusion](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/auto_v18.py#L93) · paramètres reason
- [programme](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/auto_v18.py#L182) · paramètres doc, date
- [normalize](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/auto_v18.py#L185) · paramètres s
- [np_participants](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/auto_v18.py#L189) · paramètres doc, manifest · Ne confirme zéro NP que si la liste complète, ses numéros et ses drapeaux sont interprétables.
- [update_np](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/auto_v18.py#L210) · paramètres cache, course, manifest, pmu_data
- [run](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/auto_v18.py#L225) · paramètres cache: Path, date: str, selection: list[str], max_new: int, phase: str='auto', max_discoveries: int=2, now=None, selection_complete=None, clock=None, priorites=(), production=False, prioritaire=False, actualiser_plan=None, preparation_seule=False
- [charger_participants](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/auto_v18.py#L284) · paramètres code
- [main](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/auto_v18.py#L569) · paramètres aucun

### [pmu_geny/avis_24h_trot.py](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/avis_24h_trot.py)

Imports déclarés · argparse, bs4, datetime, echeances_production, pathlib, re, unicodedata, urllib.parse, urllib.request
Point d’entrée __main__ déclaré.
- [redirect_request](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/avis_24h_trot.py#L22) · paramètres self, req, fp, code, msg, headers, newurl
- [source_autorisee](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/avis_24h_trot.py#L28) · paramètres url
- [lire_page](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/avis_24h_trot.py#L34) · paramètres url
- [normaliser](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/avis_24h_trot.py#L45) · paramètres value
- [contient](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/avis_24h_trot.py#L51) · paramètres text, terme
- [liens_index](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/avis_24h_trot.py#L56) · paramètres html
- [article](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/avis_24h_trot.py#L67) · paramètres html, titre_index, course, cheval, observed
- [collecter](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/avis_24h_trot.py#L109) · paramètres cache, *, fetch=lire_page, clock=lambda: datetime.now(timezone.utc)
- [champs_sheet](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/avis_24h_trot.py#L166) · paramètres doc, number, name, departure, now

### [pmu_geny/avis_experts_v22.py](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/avis_experts_v22.py)

Imports déclarés · __future__, auto_v18, datetime, html, html.parser, json, liaison_chevaux_v22, ml_v19, partants_actuels_v21, pathlib, re, unicodedata, urllib.request
- [nom_normalise](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/avis_experts_v22.py#L19) · paramètres value
- [url_quinte](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/avis_experts_v22.py#L27) · paramètres day
- [_fetch_zone](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/avis_experts_v22.py#L32) · paramètres url
- [__init__](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/avis_experts_v22.py#L42) · paramètres self
- [handle_starttag](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/avis_experts_v22.py#L45) · paramètres self, tag, attrs
- [handle_data](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/avis_experts_v22.py#L56) · paramètres self, data
- [handle_endtag](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/avis_experts_v22.py#L58) · paramètres self, tag
- [parser_zone_quinte](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/avis_experts_v22.py#L66) · paramètres html, course, participants · Ne retenir que le Quinté dont hippodrome et nom sont attestés dans la page.
- [parser_zone_profils](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/avis_experts_v22.py#L113) · paramètres html, course, participants · Profil hippique de la page officielle Zone-Turf, seulement course vérifiée.
- [_pmu_opinion](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/avis_experts_v22.py#L155) · paramètres item · retours littéraux
- [collecter](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/avis_experts_v22.py#L166) · paramètres cache, course, raw, now=None, fetch=None · retours littéraux APRES_DEPART

### [pmu_geny/cadence_geny.py](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/cadence_geny.py)

Imports déclarés · datetime, echeances_production, email.utils
- [reprise_serveur](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/cadence_geny.py#L15) · paramètres value, now
- [__init__](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/cadence_geny.py#L28) · paramètres self, cache
- [intervalle](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/cadence_geny.py#L37) · paramètres self
- [delai](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/cadence_geny.py#L40) · paramètres self, now
- [_sauver](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/cadence_geny.py#L44) · paramètres self
- [reserver](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/cadence_geny.py#L51) · paramètres self, now
- [terminer](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/cadence_geny.py#L58) · paramètres self, now, *, valide=None, refus=False

### [pmu_geny/carriere_geny.py](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/carriere_geny.py)

Imports déclarés · datetime, ferrures_geny, re, zoneinfo
- [confirmer_inedit](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/carriere_geny.py#L9) · paramètres document, html, ident
- [walk](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/carriere_geny.py#L18) · paramètres value

### [pmu_geny/collecte_geny_v4.py](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/collecte_geny_v4.py)

Imports déclarés · __future__, argparse, carriere_geny, csv, datetime, ferrures_geny, json, pathlib, playwright.sync_api, re, structure_geny, sys
Point d’entrée __main__ déclaré.
- [normalize](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/collecte_geny_v4.py#L25) · paramètres s: str
- [dismiss_consent](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/collecte_geny_v4.py#L29) · paramètres page · Cliquer seulement sur le refus explicite du bandeau, jamais sur l'acceptation. · retours littéraux NON_VISIBLE, REFUSE
- [separer_qualifications](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/collecte_geny_v4.py#L56) · paramètres candidat: str · Retirer une qualification (hors course) et sa date des donnees de course.
- [lire_classement](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/collecte_geny_v4.py#L79) · paramètres cellules: list[str] · Lire uniquement le classement de fin de ligne, jamais une cote ou allocation. · retours littéraux
- [parse_career](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/collecte_geny_v4.py#L113) · paramètres body: str, dom_rows: list[str] · Extrait les dates de courses de carriere en privilegiant les lignes DOM.
- [limitation_geny](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/collecte_geny_v4.py#L205) · paramètres status: int &#124; None, title: str, visible_text: str · Le site peut renvoyer une page 429 avec un statut HTTP 200.
- [diagnostic_acces](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/collecte_geny_v4.py#L217) · paramètres status: int &#124; None, title: str, text: str, html: str · Classer la page existante sans lancer aucune nouvelle requete HTTP. · retours littéraux ACCES_LIMITE_429, ACCES_REFUSE_403, CARRIERE_ACCESSIBLE, CARRIERE_NON_DETECTEE
- [enregistrer_acces](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/collecte_geny_v4.py#L243) · paramètres outdir: Path, verdict: str, url: str, status: int &#124; None, title: str, cookie_status: str='NON_TESTE'
- [sauvegarder_diagnostics](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/collecte_geny_v4.py#L255) · paramètres page, outdir: Path, text: str
- [sauver_refus_ou_limitation](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/collecte_geny_v4.py#L260) · paramètres outdir: Path, url: str, status: int &#124; None, titre: str, verdict: str
- [collecter_page](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/collecte_geny_v4.py#L269) · paramètres page, url: str, outdir: Path, *, page_chargee=False, http_status=None · Lire dans la session courante ; aucune reconnexion ni navigation de secours.
- [main](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/collecte_geny_v4.py#L392) · paramètres aucun

### [pmu_geny/contexte_meteo_v20.py](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/contexte_meteo_v20.py)

Imports déclarés · __future__, datetime, json, math, pathlib, re, unicodedata, urllib.parse, urllib.request
- [_get_json](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/contexte_meteo_v20.py#L35) · paramètres url, timeout=15
- [_norm](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/contexte_meteo_v20.py#L48) · paramètres s
- [_resolve_location](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/contexte_meteo_v20.py#L53) · paramètres cache: Path, hippodrome: str · Géocodage d'une ville FR, jamais un résultat approximatif ambigu.
- [_load](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/contexte_meteo_v20.py#L82) · paramètres path, default=None
- [_save](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/contexte_meteo_v20.py#L87) · paramètres path, doc
- [collecter_meteo](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/contexte_meteo_v20.py#L92) · paramètres cache, course, now=None, request_json=None, resolve_location=None · Retourne un statut explicite; injecte des observations numériques horodatées. · retours littéraux APRES_DEPART, METEO_RECENTE

### [pmu_geny/controle_historique.py](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/controle_historique.py)

Imports déclarés · __future__, collections, typing
- [classifier](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/controle_historique.py#L13) · paramètres result: dict[str, Any]
- [cle_ligne](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/controle_historique.py#L34) · paramètres r

### [pmu_geny/controle_sync_sheets.py](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/controle_sync_sheets.py)

Imports déclarés · collections, datetime, json, lectures_sheets, math, os, pathlib, sync_google_sheets, urllib.parse
- [cle_sportive](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/controle_sync_sheets.py#L19) · paramètres row · Identite independante de la provenance ; ignorer les lignes incomplètes.
- [journaliser](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/controle_sync_sheets.py#L31) · paramètres report
- [bloquer](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/controle_sync_sheets.py#L47) · paramètres report, motif
- [inventaire](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/controle_sync_sheets.py#L53) · paramètres headers, rows
- [lire_cles_independantes](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/controle_sync_sheets.py#L65) · paramètres session, base, tab, properties, headers · Contrôle étroit séparé : ne pas se fier uniquement à la lecture des lignes.
- [verifier_source](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/controle_sync_sheets.py#L88) · paramètres incoming
- [verifier_avant](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/controle_sync_sheets.py#L95) · paramètres headers, existing, incoming, appends, *, full_source=False, observed_keys=None
- [verifier_apres](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/controle_sync_sheets.py#L151) · paramètres control, rows

### [pmu_geny/cotes_v19.py](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/cotes_v19.py)

Imports déclarés · auto_v18, collections, datetime, fcntl, hashlib, math, ml_v19, partants_actuels_v21, pathlib, tempfile
- [instant](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/cotes_v19.py#L15) · paramètres value
- [cote_valide](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/cotes_v19.py#L23) · paramètres value
- [_rapport](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/cotes_v19.py#L32) · paramètres participant, observed=None, depart=None, *, diagnostic=None
- [extraire_cote](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/cotes_v19.py#L73) · paramètres participant
- [dernier_releve](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/cotes_v19.py#L78) · paramètres cache, course · Relire aussi les archives V19 dont le dernier instantané était incomplet.
- [_nouveaux_partants](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/cotes_v19.py#L100) · paramètres participants, observed, depart, diagnostic
- [_chemin_verrou](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/cotes_v19.py#L130) · paramètres cache, key
- [collecter](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/cotes_v19.py#L136) · paramètres cache, course, participants, now=None · retours littéraux APRES_DEPART_SANS_RELEVE
- [_actualiser](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/cotes_v19.py#L159) · paramètres path, course, old, incoming, now, diagnostic
- [calculer_cotes](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/cotes_v19.py#L208) · paramètres cache, course, now, clock=None · Publier le marché à partir du relevé canonique, avec versions pré-départ. · retours littéraux ANCIEN_RELEVE_PLUS_COMPLET, APRES_DEPART, DONNEES_INSUFFISANTES, RELEVE_PLUS_RECENT

### [pmu_geny/cycle_ml.py](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/cycle_ml.py)

Imports déclarés · __future__, argparse, cycle_ml_actif, cycle_ml_experimental, datetime, hashlib, json, maturite_ml, ml_v19, pathlib, performance_prospective, zoneinfo
Point d’entrée __main__ déclaré.
- [run](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/cycle_ml.py#L16) · paramètres cache, now=None, force=False
- [main](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/cycle_ml.py#L62) · paramètres aucun

### [pmu_geny/cycle_ml_actif.py](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/cycle_ml_actif.py)

Imports déclarés · argparse, datetime, experience_ml, hashlib, joblib, json, ml_v19, numpy, pathlib
Point d’entrée __main__ déclaré.
- [modele_actif](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/cycle_ml_actif.py#L14) · paramètres name
- [entrainer](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/cycle_ml_actif.py#L20) · paramètres cache, now=None
- [modele_disponible](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/cycle_ml_actif.py#L69) · paramètres cache
- [main](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/cycle_ml_actif.py#L79) · paramètres aucun

### [pmu_geny/cycle_ml_experimental.py](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/cycle_ml_experimental.py)

Imports déclarés · datetime, experience_ml, ml_v19, pathlib
- [executer](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/cycle_ml_experimental.py#L7) · paramètres cache, now, empreinte

### [pmu_geny/cycle_production.py](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/cycle_production.py)

Imports déclarés · auto_v18, datetime, echeances_production, rapprochement_reunions
- [executer](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/cycle_production.py#L9) · paramètres cache, plan_path, clock=lambda: datetime.now(timezone.utc)
- [preparer](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/cycle_production.py#L13) · paramètres aucun
- [actualiser](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/cycle_production.py#L32) · paramètres aucun

### [pmu_geny/dates_registre.py](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/dates_registre.py)

Imports déclarés · dashboard.trot_analytics.dates, sync_google_sheets
- [libelle_paris](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/dates_registre.py#L13) · paramètres field, label
- [projection](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/dates_registre.py#L19) · paramètres field, value · retours littéraux
- [colonnes_projection](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/dates_registre.py#L32) · paramètres headers, labels
- [enrichir_publication](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/dates_registre.py#L45) · paramètres tab, headers, updates, appends
- [nombre_kpi](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/dates_registre.py#L57) · paramètres value, label, *, legacy=False

### [pmu_geny/decouverte_partants.py](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/decouverte_partants.py)

Imports déclarés · __future__, argparse, collecte_geny_v4, datetime, json, pathlib, playwright.sync_api, re, time, urllib.parse
Point d’entrée __main__ déclaré.
- [write_json](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/decouverte_partants.py#L23) · paramètres file: Path, obj
- [links](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/decouverte_partants.py#L28) · paramètres page
- [race_candidates](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/decouverte_partants.py#L32) · paramètres anchors, keyword
- [candidate_urls](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/decouverte_partants.py#L42) · paramètres urls
- [get_rows](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/decouverte_partants.py#L56) · paramètres page · Lit les tr HTML sans supposer que le nom est un href.
- [participants_from_rows](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/decouverte_partants.py#L72) · paramètres rows
- [try_direct_url](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/decouverte_partants.py#L86) · paramètres page, row_index
- [click_get_horse_url](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/decouverte_partants.py#L94) · paramètres page, context, row_index, name, diagnostic, number · Clique uniquement dans la cellule du nom et suit popup OU navigation locale.
- [extract_partants](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/decouverte_partants.py#L143) · paramètres page, context, race_id, attendu, diagnostic
- [produire_manifest](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/decouverte_partants.py#L180) · paramètres race_url, programme, attendu, output, diagnostic, keyword, etat_path=None
- [main](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/decouverte_partants.py#L250) · paramètres aucun

### [pmu_geny/departs_trot.py](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/departs_trot.py)

Imports déclarés · re, selection_metier_v20_4
- [mode_explicite](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/departs_trot.py#L14) · paramètres raw · retours littéraux , Autostart, Volté
- [mode_pmu](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/departs_trot.py#L23) · paramètres course
- [entier](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/departs_trot.py#L37) · paramètres value, minimum=1, maximum=5000
- [depart_partant_pmu](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/departs_trot.py#L43) · paramètres course, participant
- [depart_historique_geny](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/departs_trot.py#L68) · paramètres course, participation

### [pmu_geny/echeances_production.py](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/echeances_production.py)

Imports déclarés · __future__, argparse, collections, dashboard.trot_analytics.dates, datetime, hashlib, ipr, ipr_prospectif, json, maturite_ml, os, pathlib, rapprochement_reunions, re
Point d’entrée __main__ déclaré.
- [lire](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/echeances_production.py#L24) · paramètres path
- [sauver](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/echeances_production.py#L31) · paramètres path, value
- [courses_du_jour](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/echeances_production.py#L39) · paramètres cache, now
- [course_annulee](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/echeances_production.py#L47) · paramètres course
- [identite_course](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/echeances_production.py#L51) · paramètres course · Caractéristiques indépendantes de l'heure annoncée dans le programme PMU.
- [reunions_du_jour](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/echeances_production.py#L57) · paramètres cache, day, *, inventaire=None
- [creneau_nocturne](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/echeances_production.py#L85) · paramètres now
- [profil_preparation_disponible](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/echeances_production.py#L92) · paramètres cache, date, course, now
- [preparation_nocturne](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/echeances_production.py#L104) · paramètres cache, now
- [planifier](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/echeances_production.py#L121) · paramètres cache, now, force=False
- [besoin_pmu](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/echeances_production.py#L182) · paramètres cache, now · Réserver le créneau avant une échéance, même si le cron est retardé. · retours littéraux ECHEANCE_PMU_PRIORITAIRE
- [limite_collecte_nocturne](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/echeances_production.py#L197) · paramètres cache, now
- [motif_pause_collecte_nocturne](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/echeances_production.py#L217) · paramètres cache, now
- [budget_collecte_nocturne](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/echeances_production.py#L221) · paramètres cache, now
- [etat_cooldown_geny](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/echeances_production.py#L226) · paramètres cache, now, *, prod=None, back=None · Dater l'observation et conserver l'échéance, même après expiration.
- [pause_geny_active](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/echeances_production.py#L251) · paramètres cache, now, *, prod=None, back=None
- [plan_collecte](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/echeances_production.py#L256) · paramètres cache, now, *, nocturne=False · Contrôle léger avant installation du navigateur et des dépendances.
- [relais_historiques](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/echeances_production.py#L279) · paramètres cache, now, plan, *, nocturne=False · Relayer seulement après une tâche PMU utile et persistée.
- [relais_nocturne](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/echeances_production.py#L295) · paramètres cache, now, plan
- [prevision_valide](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/echeances_production.py#L299) · paramètres doc, depart, now, ml=False, key=None
- [preuves_sheets](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/echeances_production.py#L322) · paramètres rows, now, *, observations_verifiees=False · Reconstituer les sélections effectivement lisibles dans le registre.
- [enregistrer_publication](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/echeances_production.py#L358) · paramètres cache, now, plan, publie, *, sheets=None · Appeler après Sheets : une tentative ou un calcul seul ne vaut pas publication.
- [main](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/echeances_production.py#L561) · paramètres aucun

### [pmu_geny/evaluation_geny.py](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/evaluation_geny.py)

Imports déclarés · argparse, collections, cycle_ml_actif, datetime, echeances_production, experience_ml, json, liaison_chevaux_v22, ml_v19, pathlib, signaux_geny
Point d’entrée __main__ déclaré.
- [indexer_captures](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/evaluation_geny.py#L16) · paramètres cache, ids
- [reconstruire](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/evaluation_geny.py#L33) · paramètres cache, rows
- [rejouer_classements](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/evaluation_geny.py#L70) · paramètres cache, groups, mode
- [rejouer_ml](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/evaluation_geny.py#L125) · paramètres rows
- [bilan](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/evaluation_geny.py#L154) · paramètres cache, now
- [summary](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/evaluation_geny.py#L162) · paramètres results

### [pmu_geny/experience_ml.py](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/experience_ml.py)

Imports déclarés · __future__, argparse, collections, datetime, echeances_production, hashlib, joblib, json, liaison_chevaux_v22, maturite_ml, ml_v19, numpy, pathlib, performance_prospective, profils_partants, sklearn.base, sklearn.ensemble, sklearn.impute, sklearn.linear_model, sklearn.metrics, sklearn.pipeline, sklearn.preprocessing
Point d’entrée __main__ déclaré.
- [split_days](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/experience_ml.py#L27) · paramètres records, validation_day, test_day
- [admissible](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/experience_ml.py#L45) · paramètres cache, as_of · Valide les etiquettes et la chronologie sans modifier les captures.
- [matrix](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/experience_ml.py#L54) · paramètres rows, fields=FEATURES
- [summary](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/experience_ml.py#L59) · paramètres hits
- [evaluate](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/experience_ml.py#L68) · paramètres rows, scores
- [evaluate_hybrid](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/experience_ml.py#L81) · paramètres rows, direct_scores, ml_scores · Combiner les deux rangs à poids égaux sur le même relevé.
- [paired_interval](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/experience_ml.py#L95) · paramètres left, right
- [modeles](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/experience_ml.py#L107) · paramètres aucun · Même définition déterministe pour l'évaluation et l'apprentissage actif.
- [tester_profils_ml](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/experience_ml.py#L120) · paramètres model, train, validation, test · Comparer les ajouts sur les mêmes partants, hors entraînement.
- [tester_profils_direct](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/experience_ml.py#L150) · paramètres cache, test · Isoler le départage sur les versions Direct certifiées et relues dans Sheets.
- [ordre](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/experience_ml.py#L198) · paramètres h
- [run](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/experience_ml.py#L224) · paramètres cache, output, validation_day, test_day, now=None, *, select_research=False
- [latest_label](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/experience_ml.py#L235) · paramètres rows
- [earliest_capture](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/experience_ml.py#L237) · paramètres rows
- [main](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/experience_ml.py#L420) · paramètres aucun

### [pmu_geny/export_v17.py](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/export_v17.py)

Imports déclarés · __future__, argparse, csv, json, pathlib
Point d’entrée __main__ déclaré.
- [_json](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/export_v17.py#L20) · paramètres path: Path, fallback=None
- [_write](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/export_v17.py#L26) · paramètres path: Path, cols: list[str], records: list[dict]
- [exporter](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/export_v17.py#L36) · paramètres manifest: dict, cache: Path, sorties: Path
- [main](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/export_v17.py#L82) · paramètres aucun

### [pmu_geny/extraction_historique_par_cheval.py](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/extraction_historique_par_cheval.py)

Imports déclarés · __future__, collecte_geny_v4, json, pathlib, re, sys, typing
- [extraire_cheval](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/extraction_historique_par_cheval.py#L15) · paramètres url: str, identifiant: str, sortie: Path, *, page=None, page_chargee=False, http_status=None

### [pmu_geny/ferrures_geny.py](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/ferrures_geny.py)

Imports déclarés · __future__, bs4, collecte_geny_v4, collections, datetime, departs_trot, echeances_production, json, re, unicodedata
- [normaliser](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/ferrures_geny.py#L18) · paramètres value
- [libelle_ferrure](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/ferrures_geny.py#L23) · paramètres value · retours littéraux D4, DA/PP, DP/PA, F, P4
- [flux_next](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/ferrures_geny.py#L41) · paramètres html · Assembler les fragments de données Next.js sans exécuter de JavaScript.
- [documents](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/ferrures_geny.py#L53) · paramètres html
- [participations](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/ferrures_geny.py#L79) · paramètres html, ident
- [walk](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/ferrures_geny.py#L81) · paramètres value
- [cle_performance](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/ferrures_geny.py#L97) · paramètres row
- [observations](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/ferrures_geny.py#L102) · paramètres html, ident
- [manquantes](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/ferrures_geny.py#L165) · paramètres doc
- [couverture](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/ferrures_geny.py#L170) · paramètres doc
- [enrichir](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/ferrures_geny.py#L176) · paramètres doc, html, ident, source_url, capture_utc=None

### [pmu_geny/formes_contextuelles_v32.py](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/formes_contextuelles_v32.py)

Imports déclarés · __future__, datetime, departs_trot, echeances_production, partants_actuels_v21, re, selection_metier_v20_4, statistics, top3_independants_v22
- [_discipline](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/formes_contextuelles_v32.py#L20) · paramètres value · retours littéraux a, m
- [_classement](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/formes_contextuelles_v32.py#L29) · paramètres value
- [_musique_pmu](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/formes_contextuelles_v32.py#L39) · paramètres participant, discipline · Le PMU indique la discipline par 'a'/'m'; ne pas melanger les deux.
- [_distance_factor](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/formes_contextuelles_v32.py#L63) · paramètres d1, d2
- [_facteur_niveau](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/formes_contextuelles_v32.py#L77) · paramètres course, row · L'allocation est un proxy imparfait du niveau, jamais un classement etabli.
- [_historique_contextuel](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/formes_contextuelles_v32.py#L95) · paramètres historique, course, profil, *, ferrure_differente=0.65, ferrure_inconnue=0.85, mode_depart=None, observation=None · Pondere les performances passees selon les conditions de la course cible.
- [chronos_comparables](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/formes_contextuelles_v32.py#L174) · paramètres historique, course · Médiane des réductions Geny sur le même hippodrome, discipline et distance proche.
- [forme_meme_depart](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/formes_contextuelles_v32.py#L213) · paramètres historique, course, profil, observation
- [noter_partant](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/formes_contextuelles_v32.py#L225) · paramètres participant, course, lien, profil · Score toujours explicable: PMU seul, Geny seul ou melange prudent.

### [pmu_geny/historique_individuel.py](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/historique_individuel.py)

Imports déclarés · argparse, bs4, cadence_geny, collecte_geny_v4, controle_historique, datetime, decouverte_partants, echeances_production, extraction_historique_par_cheval, ferrures_geny, json, liaison_chevaux_v22, liens_geny_course, pathlib, playwright.sync_api, re, time, urllib.parse, zoneinfo
Point d’entrée __main__ déclaré.
- [cliquer_nom](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/historique_individuel.py#L18) · paramètres cell, nom
- [candidats_recherche](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/historique_individuel.py#L25) · paramètres html, nom
- [rechercher](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/historique_individuel.py#L65) · paramètres horse, page
- [resolve](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/historique_individuel.py#L104) · paramètres horse, out, page=None
- [ouvrir_source](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/historique_individuel.py#L129) · paramètres horse, out, page
- [nom_fiche](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/historique_individuel.py#L202) · paramètres html, ident · retours littéraux
- [verifier_candidat](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/historique_individuel.py#L216) · paramètres horse, url, status, text, out · Un ID déjà recensé donne une URL candidate, jamais une identité acceptée.
- [observer_http_geny](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/historique_individuel.py#L230) · paramètres context, out=None
- [persister_mesure](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/historique_individuel.py#L235) · paramètres aucun
- [geny](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/historique_individuel.py#L239) · paramètres url
- [requete](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/historique_individuel.py#L243) · paramètres request
- [reponse](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/historique_individuel.py#L248) · paramètres response
- [collecter](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/historique_individuel.py#L265) · paramètres horse, out
- [navigation](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/historique_individuel.py#L276) · paramètres response
- [main](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/historique_individuel.py#L322) · paramètres aucun

### [pmu_geny/historique_kpi.py](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/historique_kpi.py)

Imports déclarés · dashboard.trot_analytics.dates, dates_registre, datetime, json, kpi_registre, lectures_sheets, migration_dates_sheets, moteur_sheets, sync_google_sheets, urllib.parse, zoneinfo
- [planifier](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/historique_kpi.py#L15) · paramètres source, existing, now
- [enregistrer](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/historique_kpi.py#L55) · paramètres engine, tables, now=None

### [pmu_geny/historiques_incrementaux.py](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/historiques_incrementaux.py)

Imports déclarés · ., __future__, argparse, cadence_geny, collections, controle_historique, controle_sync_sheets, csv, datetime, echeances_production, ferrures_geny, hashlib, historiques_partiels, identites_chevaux, json, liaison_chevaux_v22, liens_geny_course, moteur_sheets, os, pathlib, preparation_prochaines, rapprochement_v20_6, rattrapage_historiques, re, recensement_historiques, shutil, structure_geny, subprocess, sys, tempfile, time, zoneinfo
Point d’entrée __main__ déclaré.
- [lire](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/historiques_incrementaux.py#L33) · paramètres path, default=None
- [ecrire](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/historiques_incrementaux.py#L41) · paramètres path, doc
- [instant](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/historiques_incrementaux.py#L49) · paramètres value
- [capture_valide](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/historiques_incrementaux.py#L57) · paramètres cache, ident
- [actualisation_requise](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/historiques_incrementaux.py#L62) · paramètres horse, now, ttl_heures=24 · retours littéraux , FERRURES_HISTORIQUES_A_COMPLETER, HISTORIQUE_ABSENT_OU_NON_DATE, NOUVELLE_COURSE_OFFICIELLE, PUBLICATION_GENY_EN_ATTENTE, VERIFICATION_PERIODIQUE
- [priorite_engagement](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/historiques_incrementaux.py#L78) · paramètres horse, now, *, manquant
- [course_geny_connue](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/historiques_incrementaux.py#L93) · paramètres cache, engagement · Rapprocher un engagement à partir des seules preuves déjà sauvegardées. · retours littéraux
- [alimenter](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/historiques_incrementaux.py#L115) · paramètres cache, now, *, sauvegarder=True, engagements=None, associations=None · PMU est la liste de référence ; les manifests ne servent qu'à l'identité Geny.
- [materialiser_manifestes](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/historiques_incrementaux.py#L214) · paramètres cache, state · Reconstruire hors réseau les manifests une fois toutes les identités établies.
- [prochaine_tache](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/historiques_incrementaux.py#L250) · paramètres state, now, attempts
- [executer_enfant](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/historiques_incrementaux.py#L289) · paramètres horse, out
- [memoriser_resolution](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/historiques_incrementaux.py#L298) · paramètres horse, report, out, *, cache=None · Une résolution de lien n'est jamais une validation de carrière.
- [accepter](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/historiques_incrementaux.py#L327) · paramètres cache, horse, report, *, origine='COLLECTE_INCREMENTALE_PRODUCTION' · Ne jamais remplacer un historique complet par un partiel ou une régression.
- [indexed](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/historiques_incrementaux.py#L346) · paramètres d
- [suspendre_geny](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/historiques_incrementaux.py#L411) · paramètres cache, state, stamp, code, reprise_serveur=None
- [checkpoint_distant](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/historiques_incrementaux.py#L425) · paramètres cache, *, queue=QUEUE · Publier seulement les fichiers de collecte sous le verrou partagé des workflows.
- [git](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/historiques_incrementaux.py#L428) · paramètres *args, cwd=root
- [run](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/historiques_incrementaux.py#L464) · paramètres cache, *, max_minutes=15, max_chevaux=None, publier=False, collect=None, checkpoint=None, sync=None, mode='production', stop_requested=None, prochains_depart=False, creneau_reserve=None, nocturne=False, perimetre=None, archive_recensement=None, cadence_geny=None
- [save](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/historiques_incrementaux.py#L522) · paramètres *, distant=True
- [main](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/historiques_incrementaux.py#L797) · paramètres aucun

### [pmu_geny/historiques_partiels.py](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/historiques_partiels.py)

Imports déclarés · ., controle_historique, datetime, ferrures_geny, hashlib, json, liaison_chevaux_v22, pathlib, re, urllib.parse, zoneinfo
- [conserver](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/historiques_partiels.py#L14) · paramètres cache, horse, report

### [pmu_geny/identites_chevaux.py](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/identites_chevaux.py)

Imports déclarés · collections, controle_sync_sheets, datetime, functools, historiques_incrementaux, json, liaison_chevaux_v22, ml_v19, pathlib, re, urllib.parse
- [source_identifiant](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/identites_chevaux.py#L18) · paramètres ident, url · retours littéraux
- [correspondances](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/identites_chevaux.py#L32) · paramètres aucun
- [courses_verifiees](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/identites_chevaux.py#L58) · paramètres aucun
- [qualifier_observation](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/identites_chevaux.py#L62) · paramètres record · Conserver la provenance ; appliquer seulement une liaison déjà vérifiée.
- [canoniser_ligne](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/identites_chevaux.py#L94) · paramètres row
- [cle_inter_sources](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/identites_chevaux.py#L102) · paramètres row · Même performance attestée : seule la notation des secondes est normalisée.
- [__init__](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/identites_chevaux.py#L113) · paramètres self, cache, *, observations=None
- [ajouter](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/identites_chevaux.py#L208) · paramètres self, nom, ident, url, preuve, course=None, numero=None, *, fiche=None
- [resoudre](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/identites_chevaux.py#L227) · paramètres self, nom, course=None, numero=None, *, nom_repris=False, annee=None
- [preuve_resolution_valide](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/identites_chevaux.py#L246) · paramètres proof

### [pmu_geny/index_geny_apres_publication.py](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/index_geny_apres_publication.py)

Imports déclarés · argparse, datetime, echeances_production, pathlib, rapprochement_v20_6, zoneinfo
Point d’entrée __main__ déclaré.
- [dates_a_traiter](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/index_geny_apres_publication.py#L12) · paramètres cache, plan, now
- [run](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/index_geny_apres_publication.py#L33) · paramètres cache, plan, clock=None, fetch=None
- [main](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/index_geny_apres_publication.py#L48) · paramètres aucun

### [pmu_geny/ipr.py](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/ipr.py)

Imports déclarés · auto_v18, collections, dashboard.trot_analytics.usages, datetime, departs_trot, echeances_production, formes_contextuelles_v32, liaison_chevaux_v22, math, os, partants_actuels_v21, pathlib, profils_partants, re, selection_metier_v20_4, signaux_geny
- [actif](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/ipr.py#L22) · paramètres aucun
- [piste](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/ipr.py#L26) · paramètres value · retours littéraux GP, PP
- [evaluer_cheval](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/ipr.py#L35) · paramètres course, profil, lien, observation · Score sur 100, confiance descriptive et motifs explicites.
- [calculer](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/ipr.py#L134) · paramètres course, profils, liens, observation, calcul
- [enregistrer](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/ipr.py#L176) · paramètres cache, course, raw, observation, clock · retours littéraux CALCULE, DEJA_CALCULE, HORS_COUPURE, PARTANTS_PMU_INCOHERENTS, RELEVE_NON_FRAIS

### [pmu_geny/ipr_prospectif.py](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/ipr_prospectif.py)

Imports déclarés · collections, dashboard.trot_analytics.dates, dashboard.trot_analytics.usages, datetime, echeances_production, experience_ml, hashlib, ipr, pathlib, performance_prospective, statistics, sync_google_sheets
- [donnees_sheets](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/ipr_prospectif.py#L15) · paramètres rows
- [certifier](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/ipr_prospectif.py#L28) · paramètres cache, plan, sheets
- [podium_verifie](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/ipr_prospectif.py#L67) · paramètres arrival, key, depart, now
- [mesurer](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/ipr_prospectif.py#L79) · paramètres cache, now

### [pmu_geny/kpi_registre.py](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/kpi_registre.py)

Imports déclarés · auto_v18, collections, cotes_v19, datetime, echeances_production, json, liaison_chevaux_v22, math, partants_actuels_v21, pathlib, rapprochement_reunions, rattrapage_historiques, statistics, sync_google_sheets
- [_load](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/kpi_registre.py#L12) · paramètres path
- [_nombre](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/kpi_registre.py#L16) · paramètres value
- [calculer_kpi](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/kpi_registre.py#L22) · paramètres cache, source=None, now=None, *, sheets_courses=None · retours littéraux
- [ferrure_sourcee](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/kpi_registre.py#L61) · paramètres row · retours littéraux
- [nonempty](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/kpi_registre.py#L69) · paramètres field
- [metric](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/kpi_registre.py#L70) · paramètres label, value, definition
- [totaux_reference](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/kpi_registre.py#L357) · paramètres metrics · Références explicites, issues du même snapshot que les numérateurs.
- [value](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/kpi_registre.py#L359) · paramètres label
- [plan_kpi](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/kpi_registre.py#L433) · paramètres values, metrics · Actualise valeur, définition et référence connue ensemble ; préserve les autres formules.

### [pmu_geny/lectures_sheets.py](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/lectures_sheets.py)

Imports déclarés · time
- [get_lecture](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/lectures_sheets.py#L5) · paramètres session, url, **kwargs

### [pmu_geny/liaison_chevaux_v22.py](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/liaison_chevaux_v22.py)

Imports déclarés · __future__, collections, historiques_incrementaux, identites_chevaux, ml_v19, pathlib, re, unicodedata
- [nom_normalise](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/liaison_chevaux_v22.py#L13) · paramètres value
- [separer_pays_pmu](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/liaison_chevaux_v22.py#L17) · paramètres nom
- [nom_geny_concordant](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/liaison_chevaux_v22.py#L23) · paramètres nom_pmu, fiche · Les suffixes de pays PMU sont confirmés par la nationalité Geny.
- [etablir](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/liaison_chevaux_v22.py#L35) · paramètres cache, course, participants=None, *, index=None

### [pmu_geny/liens_geny_course.py](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/liens_geny_course.py)

Imports déclarés · bs4, datetime, ferrures_geny, historiques_incrementaux, liaison_chevaux_v22, re, urllib.parse
- [lien_valide](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/liens_geny_course.py#L11) · paramètres url, ident=None
- [extraire](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/liens_geny_course.py#L18) · paramètres rows, html, engagement, source_url, stamp
- [ajouter](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/liens_geny_course.py#L24) · paramètres name, ident, url, source
- [parcourir](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/liens_geny_course.py#L41) · paramètres value
- [conserver_liens_precedents](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/liens_geny_course.py#L95) · paramètres proof, previous
- [memoriser](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/liens_geny_course.py#L101) · paramètres cache, horse, out
- [pour_cheval](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/liens_geny_course.py#L127) · paramètres cache, engagement, numero, nom, now, course_url

### [pmu_geny/maturite_ml.py](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/maturite_ml.py)

Imports déclarés · datetime, echeances_production, experience_ml, hashlib, joblib, ml_v19, os, pathlib
- [thresholds](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/maturite_ml.py#L30) · paramètres aucun
- [coverage](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/maturite_ml.py#L48) · paramètres rows
- [sha](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/maturite_ml.py#L62) · paramètres path
- [candidate_path](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/maturite_ml.py#L66) · paramètres cache, candidate
- [score_shadow](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/maturite_ml.py#L74) · paramètres cache, course, raw, observed, clock, *, prepared=None · Figer une seule comparaison par course et version, avant son départ.
- [certify_shadow](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/maturite_ml.py#L116) · paramètres cache, key, proof, now
- [comparisons](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/maturite_ml.py#L132) · paramètres cache, candidate, now
- [prospective](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/maturite_ml.py#L170) · paramètres rows

### [pmu_geny/migration_dates_sheets.py](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/migration_dates_sheets.py)

Imports déclarés · argparse, audit_dates_sheets, collections, dashboard.trot_analytics.dates, dates_registre, datetime, gzip, hashlib, json, lectures_sheets, math, moteur_sheets, os, pathlib, sync_google_sheets
Point d’entrée __main__ déclaré.
- [range_cell](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/migration_dates_sheets.py#L24) · paramètres sheet, row, col
- [format_cell](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/migration_dates_sheets.py#L29) · paramètres sheet, row, col, kind, note=None
- [entered](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/migration_dates_sheets.py#L38) · paramètres cell
- [raw](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/migration_dates_sheets.py#L42) · paramètres cell
- [hide_column](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/migration_dates_sheets.py#L47) · paramètres sheet, col
- [current_format](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/migration_dates_sheets.py#L54) · paramètres cell
- [same_value](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/migration_dates_sheets.py#L58) · paramètres actual, expected
- [write_column](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/migration_dates_sheets.py#L64) · paramètres sheet, col, cells, fields
- [valeurs_cellules](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/migration_dates_sheets.py#L79) · paramètres changes, kind
- [format_conforme](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/migration_dates_sheets.py#L90) · paramètres cell, kind
- [planifier](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/migration_dates_sheets.py#L95) · paramètres tab, props, rows
- [snapshot](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/migration_dates_sheets.py#L215) · paramètres engine
- [empreinte](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/migration_dates_sheets.py#L220) · paramètres snapshot_data
- [verifier](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/migration_dates_sheets.py#L233) · paramètres before, after, updates
- [relire_archive](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/migration_dates_sheets.py#L258) · paramètres archive
- [migrer](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/migration_dates_sheets.py#L265) · paramètres engine, archive, *, appliquer=False, reference=None
- [main](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/migration_dates_sheets.py#L309) · paramètres aucun

### [pmu_geny/migration_geny.py](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/migration_geny.py)

Imports déclarés · collections, dashboard.trot_analytics.usages, structure_geny, sync_google_sheets
- [planifier](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/migration_geny.py#L9) · paramètres headers, rows, archives
- [verifier](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/migration_geny.py#L43) · paramètres before, after, headers, fields, updates
- [plages_migration](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/migration_geny.py#L56) · paramètres tab, updates · Google ignore les valeurs nulles, ce qui espace les écritures sans toucher aux cellules intermédiaires.

### [pmu_geny/ml_v19.py](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/ml_v19.py)

Imports déclarés · __future__, auto_v18, avis_experts_v22, collections, cotes_v19, csv, cycle_ml_actif, datetime, echeances_production, experience_ml, formes_contextuelles_v32, hashlib, joblib, json, liaison_chevaux_v22, math, maturite_ml, numpy, partants_actuels_v21, pathlib, planification_v20_2, profils_partants, re, shutil, signaux_geny, top3_independants_v22
- [load](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/ml_v19.py#L41) · paramètres path, default=None
- [save](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/ml_v19.py#L45) · paramètres path, doc
- [numeric](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/ml_v19.py#L49) · paramètres v
- [features](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/ml_v19.py#L55) · paramètres horse, history, course, context=None, *, legacy=False · Strictement les informations antérieures à la course; champs absents = None.
- [pts](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/ml_v19.py#L85) · paramètres rank
- [avg](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/ml_v19.py#L93) · paramètres seq
- [pct](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/ml_v19.py#L94) · paramètres seq
- [_valid_context](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/ml_v19.py#L125) · paramètres cache, course, now, *, legacy=False · Contexte facultatif saisi/importé et sourcé, antérieur au départ.
- [snapshot](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/ml_v19.py#L144) · paramètres cache, course, manifest, now=None · Capture immuable pré-départ; ne remplace jamais une capture existante. · retours littéraux CAPTURE, DEJA_CAPTURE, NP_NON_VERIFIE, TROP_TARD
- [pmu_rows](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/ml_v19.py#L170) · paramètres cache, course, raw, now, *, legacy=False · Meme extraction PMU pour capture et inference; aucune requete reseau.
- [snapshot_pmu](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/ml_v19.py#L307) · paramètres cache, course, raw, now=None, clock=None, *, prepared=None · Capture immutable; les anciennes captures ne sont jamais enrichies apres coup. · retours littéraux CAPTURE_PMU, DEJA_CAPTURE, NP_NON_VERIFIE, TROP_TARD
- [dataset](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/ml_v19.py#L327) · paramètres cache, now=None · Exemples pre-depart avec podium complet et labels deja observes.
- [scores_intervenants](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/ml_v19.py#L370) · paramètres cache, now, discipline · Taux de podium lissé sur les captures PMU vérifiées des 90 derniers jours.
- [train](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/ml_v19.py#L404) · paramètres cache, min_courses=None, min_rows=None, now=None · Figer un candidat puis appliquer une décision sur une cohorte prospective.
- [finish](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/ml_v19.py#L427) · paramètres aucun
- [ranking_for](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/ml_v19.py#L537) · paramètres packed, rows
- [predict_pmu](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/ml_v19.py#L548) · paramètres cache, course, raw, now=None, clock=None, *, prepared=None · Inférence pré-départ : modèle promu, sinon candidat expérimental explicite. · retours littéraux HORS_FENETRE_DECISION, ML_NON_ENTRAINE, MODELE_CHRONOLOGIE_INVALIDE, MODELE_EXPERIMENTAL_CHRONOLOGIE_INVALIDE, MODELE_EXPERIMENTAL_INVALIDE, MODELE_NON_PROMU, MODELE_SCHEMA_OBSOLETE_REENTRAINEMENT_REQUIS, NP_NON_VERIFIE
- [predict](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/ml_v19.py#L618) · paramètres cache, course, manifest=None, now=None · Compatibilite anciens appelants : relire exclusivement le profil PMU.
- [export_comparatif](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/ml_v19.py#L628) · paramètres cache, course, manifest · CSV par partant: baseline, ML, NP, cote à l'approche du départ, arrivée.

### [pmu_geny/moteur_sheets.py](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/moteur_sheets.py)

Imports déclarés · collections, contextlib, controle_sync_sheets, dashboard.trot_analytics.dates, dashboard.trot_analytics.profils, dashboard.trot_analytics.usages, dates_registre, datetime, fcntl, google.auth.transport.requests, google.oauth2.service_account, hashlib, historique_kpi, identites_chevaux, ipr, json, kpi_registre, lectures_sheets, liaison_chevaux_v22, migration_dates_sheets, migration_geny, os, pathlib, re, structure_geny, sync_google_sheets, tempfile, time, urllib.parse
- [verrou_local](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/moteur_sheets.py#L29) · paramètres spreadsheet
- [ouvrir_session](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/moteur_sheets.py#L43) · paramètres aucun
- [regrouper_cellules](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/moteur_sheets.py#L51) · paramètres tab, updates · Regrouper les cellules contiguës d'une colonne sans écrire dans les trous.
- [formats_dates](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/moteur_sheets.py#L65) · paramètres sheet_id, headers, only=None
- [__init__](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/moteur_sheets.py#L85) · paramètres self, session
- [get](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/moteur_sheets.py#L87) · paramètres self, *args, **kwargs
- [post](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/moteur_sheets.py#L89) · paramètres self, *args, **kwargs
- [__init__](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/moteur_sheets.py#L95) · paramètres self, cache, spreadsheet, session=None
- [fermer](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/moteur_sheets.py#L101) · paramètres self
- [check](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/moteur_sheets.py#L106) · paramètres response
- [metadata](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/moteur_sheets.py#L111) · paramètres self
- [source](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/moteur_sheets.py#L117) · paramètres self
- [_formater_observations](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/moteur_sheets.py#L124) · paramètres self, tab, sheet_id, headers, groupe, *, appends=False
- [relire](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/moteur_sheets.py#L132) · paramètres aucun
- [conforme](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/moteur_sheets.py#L139) · paramètres cells, label
- [_formater_profils](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/moteur_sheets.py#L166) · paramètres self, properties, headers
- [rgb](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/moteur_sheets.py#L181) · paramètres couleur
- [meme_format](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/moteur_sheets.py#L185) · paramètres actuel, attendu
- [_synchroniser_onglet](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/moteur_sheets.py#L226) · paramètres self, tab, incoming, properties, *, full_source, allow_structure
- [migrer_structure_geny](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/moteur_sheets.py#L376) · paramètres self, sauvegarde, *, appliquer=False · Sauvegarder ou appliquer le même instantané sous le verrou du registre.
- [lire_courses](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/moteur_sheets.py#L433) · paramètres self, tables
- [_synchroniser_kpi](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/moteur_sheets.py#L444) · paramètres self, tables, source, *, relire_courses=False
- [synchroniser_tables](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/moteur_sheets.py#L541) · paramètres self, source, *, scope, full_source=False, allow_structure=False, kpi_source=None
- [synchroniser_cycle](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/moteur_sheets.py#L559) · paramètres self, include_kpi=True
- [synchroniser_cheval](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/moteur_sheets.py#L565) · paramètres self, horse, *, include_kpi=True, include_courses=True
- [inventaire_rattrapage](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/moteur_sheets.py#L580) · paramètres self · Lecture complète seule : inventaire et preuve des clés déjà publiées.
- [synchroniser_kpi](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/moteur_sheets.py#L618) · paramètres self

### [pmu_geny/partants_actuels_v21.py](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/partants_actuels_v21.py)

Imports déclarés · __future__, auto_v18, datetime, departs_trot, echeances_production, ml_v19, pathlib, re, sources_experts_v23
- [profil_pmu_exclusif](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/partants_actuels_v21.py#L23) · paramètres actual · Lecture sans mutation : un complément tiers ancien n'est plus un critère.
- [qualifier_ferrure](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/partants_actuels_v21.py#L36) · paramètres profile
- [_label](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/partants_actuels_v21.py#L52) · paramètres value · retours littéraux
- [age_valide](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/partants_actuels_v21.py#L62) · paramètres value
- [gains_valides](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/partants_actuels_v21.py#L70) · paramètres value
- [sexe_normalise](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/partants_actuels_v21.py#L87) · paramètres value
- [ferrure_normalisee](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/partants_actuels_v21.py#L97) · paramètres value · retours littéraux
- [ferrure_historique_explicite](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/partants_actuels_v21.py#L117) · paramètres value · Un code ambigu exige un champ ou libellé explicite de ferrure.
- [faux_code_ferrure_historique](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/partants_actuels_v21.py#L132) · paramètres value, code · Erreurs textuelles démontrables de l'ancien bridge, pas une valeur vide générique.
- [statut_participation](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/partants_actuels_v21.py#L138) · paramètres item · retours littéraux NON_PARTANT, NP_NON_VERIFIE, PARTANT
- [extraire_partants](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/partants_actuels_v21.py#L150) · paramètres raw, *, course=None
- [enregistrer](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/partants_actuels_v21.py#L201) · paramètres cache: Path, course: dict, raw, *, observe=None · retours littéraux PARTANTS_ACTUELS_ENREGISTRES, PARTANTS_NON_VERIFIES

### [pmu_geny/participation_pmu.py](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/participation_pmu.py)

Imports déclarés · __future__, argparse, datetime, json, pathlib, urllib.parse
Point d’entrée __main__ déclaré.
- [_read](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/participation_pmu.py#L16) · paramètres path: Path
- [enregistrer](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/participation_pmu.py#L20) · paramètres manifest: dict, dossier: Path, source_url: str, non_partants: str, liste_complete: bool=False, controle_confirme: bool=False
- [main](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/participation_pmu.py#L71) · paramètres aucun

### [pmu_geny/performance_prospective.py](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/performance_prospective.py)

Imports déclarés · datetime, departs_trot, echeances_production, experience_ml, hashlib, pathlib
- [retrouver](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/performance_prospective.py#L9) · paramètres cache, key, kind, proof
- [prevision_publiee](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/performance_prospective.py#L21) · paramètres cache, key, kind, proof, depart, *, depart_programme=None
- [evaluer_depart](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/performance_prospective.py#L43) · paramètres cache, key, certificate, departure, podium
- [mesurer](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/performance_prospective.py#L61) · paramètres cache, now=None

### [pmu_geny/persistance_production.py](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/persistance_production.py)

Imports déclarés · argparse, pathlib, shutil, subprocess, tempfile
Point d’entrée __main__ déclaré.
- [publier](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/persistance_production.py#L9) · paramètres cache, root=None · retours littéraux AUCUNE_DONNEE, DEJA_SAUVEGARDE, SAUVEGARDE
- [git](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/persistance_production.py#L14) · paramètres *args, cwd=root

### [pmu_geny/plan_retrait_resultats.py](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/plan_retrait_resultats.py)

Imports déclarés · argparse, collections, dates_registre, json, moteur_sheets, pathlib, sync_google_sheets
Point d’entrée __main__ déclaré.
- [colonnes_jalons](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/plan_retrait_resultats.py#L15) · paramètres aucun
- [planifier](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/plan_retrait_resultats.py#L20) · paramètres headers · Retourner les indices physiques sans modifier la feuille ni son schéma.
- [verifier_projection](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/plan_retrait_resultats.py#L35) · paramètres before, after, plan · Contrôler la conservation des clés, valeurs et formules hors des colonnes retirées.
- [main](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/plan_retrait_resultats.py#L51) · paramètres aucun
- [retrait_sauvegarde](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/plan_retrait_resultats.py#L58) · paramètres engine, sauvegarder, *, appliquer=False · Exécuter le plan sous verrou après sauvegarde, puis relire les valeurs et formules.
- [lire](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/plan_retrait_resultats.py#L63) · paramètres props

### [pmu_geny/planification_v20_2.py](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/planification_v20_2.py)

Imports déclarés · __future__, datetime, zoneinfo
- [decision_autorisee](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/planification_v20_2.py#L8) · paramètres now, date, depart
- [selectionner_courses](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/planification_v20_2.py#L17) · paramètres courses, now, date, selection, complet, etat, max_courses=12 · Liste des courses pertinentes par priorité, sans travailler sur des archives.

### [pmu_geny/preparation_prochaines.py](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/preparation_prochaines.py)

Imports déclarés · ., datetime, echeances_production, ferrures_geny, json, liaison_chevaux_v22, pathlib, zoneinfo
- [evaluer](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/preparation_prochaines.py#L10) · paramètres cache, now, state=None, *, nocturne=False
- [appliquer](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/preparation_prochaines.py#L97) · paramètres cache, state, now, *, nocturne=False
- [decision_fond](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/preparation_prochaines.py#L113) · paramètres cache, now, *, reserve=False, nocturne=False · Observer la même file que le worker, sans écrire ni lever un délai de réessai.
- [refuser](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/preparation_prochaines.py#L123) · paramètres reason
- [autoriser_fond](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/preparation_prochaines.py#L181) · paramètres cache, now, *, diagnostic=None, reserve=False, nocturne=False

### [pmu_geny/profils_partants.py](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/profils_partants.py)

Imports déclarés · dashboard.trot_analytics.profils, dataclasses, datetime, echeances_production, formes_contextuelles_v32, re
- [sorties_verifiees](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/profils_partants.py#L42) · paramètres course, lien, observation · Une sortie par jour non ambigu, documentée avant la décision.
- [_fenetre_documentee](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/profils_partants.py#L83) · paramètres sorties
- [_fiabilite_recente](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/profils_partants.py#L88) · paramètres sorties, maximum_pct
- [_gains_documentes](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/profils_partants.py#L98) · paramètres gains
- [detecter_crack](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/profils_partants.py#L102) · paramètres sorties, gains_euros · Un champion de Groupe I/II dont les gains et la fiabilité sont documentés.
- [detecter_haut_potentiel](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/profils_partants.py#L121) · paramètres sorties, age · Un jeune trotteur en progrès, avec des résultats proches de la distance cible.
- [evaluer_profils](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/profils_partants.py#L146) · paramètres course, lien, profil, observation · Conserver les deux décisions et les preuves du même relevé pré-départ.
- [afficher_profils](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/profils_partants.py#L195) · paramètres signal · Projeter les preuves enregistrées dans les deux colonnes existantes.

### [pmu_geny/pronostics_v18.py](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/pronostics_v18.py)

Imports déclarés · auto_v18, datetime, echeances_production, json, pathlib
- [read](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/pronostics_v18.py#L12) · paramètres file
- [_controle_np](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/pronostics_v18.py#L16) · paramètres data, expected, now · Un retrait atteste ne devient pas un partant lorsque le controle vieillit.
- [preparer_top3](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/pronostics_v18.py#L35) · paramètres cache, course, manifest, now=None · retours littéraux DEJA_FIGE, DONNEES_INSUFFISANTES, FIGE_BASELINE_EXPERIMENTALE, HORS_FENETRE_AVANT_DEPART
- [actualiser_top3_np](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/pronostics_v18.py#L91) · paramètres cache, course, manifest, now=None · Mise à jour avant départ après nouveau retrait; la référence initiale reste immuable. · retours littéraux APRES_DEPART, BASELINE_NON_FIGEE, INCHANGE, NP_NON_VERIFIE, NP_PERIME

### [pmu_geny/qualite_registre_v21.py](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/qualite_registre_v21.py)

Imports déclarés · argparse, collections, json, pathlib, sync_google_sheets
Point d’entrée __main__ déclaré.
- [evaluer](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/qualite_registre_v21.py#L13) · paramètres cache, debut='2026-11-12'
- [main](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/qualite_registre_v21.py#L63) · paramètres aucun

### [pmu_geny/rapprochement_reunions.py](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/rapprochement_reunions.py)

Imports déclarés · auto_v18, collections, datetime, echeances_production, functools, hashlib, json, pathlib, performance_prospective, resultats_v18, subprocess
- [inventaire_confirme](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/rapprochement_reunions.py#L17) · paramètres record
- [programmes_archives](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/rapprochement_reunions.py#L33) · paramètres date
- [revision_preuves](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/rapprochement_reunions.py#L49) · paramètres reunion
- [relecture_preuves_due](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/rapprochement_reunions.py#L56) · paramètres reunion, record
- [depart_archive](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/rapprochement_reunions.py#L61) · paramètres cache, key, method, proof, identite
- [planifier_rapprochements](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/rapprochement_reunions.py#L80) · paramètres cache, now, *, prochaines=None
- [podium_officiel](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/rapprochement_reunions.py#L116) · paramètres cache, key, depart, now
- [comparer](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/rapprochement_reunions.py#L126) · paramètres cache, key, depart, podium, certificat, *, rejets=None, course=None
- [rattraper_obligations](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/rapprochement_reunions.py#L158) · paramètres cache, plan_path, clock=lambda: datetime.now(timezone.utc) · Préserver les obligations du plan et inclure celles échues pendant le cycle.
- [rapprocher](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/rapprochement_reunions.py#L172) · paramètres cache, plan, clock=lambda: datetime.now(timezone.utc)
- [aggreger](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/rapprochement_reunions.py#L254) · paramètres rows

### [pmu_geny/rapprochement_v20_6.py](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/rapprochement_v20_6.py)

Imports déclarés · __future__, auto_v18, collecte_geny_v4, datetime, difflib, pathlib, playwright.sync_api, re, selection_metier_v20_4, unicodedata, urllib.parse
- [norm](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/rapprochement_v20_6.py#L20) · paramètres value
- [tokens](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/rapprochement_v20_6.py#L26) · paramètres value
- [nom_course_url](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/rapprochement_v20_6.py#L30) · paramètres url · Extraire la partie «prix...» du slug quand elle existe.
- [_numero](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/rapprochement_v20_6.py#L37) · paramètres value
- [_meme_hippodrome](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/rapprochement_v20_6.py#L48) · paramètres course, candidate
- [_meme_date](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/rapprochement_v20_6.py#L55) · paramètres course, candidate
- [index_from_anchors](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/rapprochement_v20_6.py#L59) · paramètres anchors, date · Dédupliquer les liens du programme sans charger les pages individuelles.
- [similarity](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/rapprochement_v20_6.py#L100) · paramètres course, candidate · Renvoie score et preuves; écarte une contradiction hippodrome évidente.
- [_nom_fortement_identique](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/rapprochement_v20_6.py#L127) · paramètres course, candidate · Preuve de nom très forte, indépendante de la numérotation R/C.
- [rapprocher](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/rapprochement_v20_6.py#L141) · paramètres course, candidats, seuil=0.83, ecart=0.12 · Associer date + hippodrome + nom ; R/C n'est qu'une preuve additionnelle.
- [liens_programme_avec_contexte](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/rapprochement_v20_6.py#L210) · paramètres page · Extraire les codes R/C seulement quand le DOM montre un contexte univoque.
- [index_programme](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/rapprochement_v20_6.py#L237) · paramètres cache, date, etat_path, ttl_heures=6 · Interroger le programme une fois par TTL, pas une fois par course.

### [pmu_geny/rattrapage_historiques.py](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/rattrapage_historiques.py)

Imports déclarés · ., __future__, argparse, auto_v18, collections, datetime, echeances_production, ferrures_geny, functools, hashlib, identites_chevaux, json, kpi_registre, liaison_chevaux_v22, moteur_sheets, os, partants_actuels_v21, pathlib, preparation_prochaines, re, reconcilier_identites_sheets, requests, resolution_identites_courses, revalider_diagnostics, sync_google_sheets, time, urllib.parse
Point d’entrée __main__ déclaré.
- [engagement_canonique](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/rattrapage_historiques.py#L23) · paramètres value
- [cle_contexte](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/rattrapage_historiques.py#L29) · paramètres horse
- [contexte_verifiable](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/rattrapage_historiques.py#L35) · paramètres horse
- [url_cheval](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/rattrapage_historiques.py#L42) · paramètres url, ident
- [url_course](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/rattrapage_historiques.py#L48) · paramètres url
- [inventaire_local](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/rattrapage_historiques.py#L53) · paramètres cache, sheets, *, index=None · Toutes les dates, NP inclus ; un nom ambigu n'est pas un identifiant.
- [merge](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/rattrapage_historiques.py#L89) · paramètres target, record
- [actualiser_inventaire](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/rattrapage_historiques.py#L134) · paramètres cache, now · Extension explicite et traçable du lot ; jamais un inventaire glissant.
- [nom_reference](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/rattrapage_historiques.py#L168) · paramètres nom
- [arrivees_verifiees](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/rattrapage_historiques.py#L172) · paramètres cache, now
- [profils_passe](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/rattrapage_historiques.py#L182) · paramètres cache, race
- [recuperer_listes_manquantes](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/rattrapage_historiques.py#L190) · paramètres cache, now, stop_requested · Compléter trois listes au maximum, uniquement pendant l'extension manuelle.
- [courses_passees](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/rattrapage_historiques.py#L223) · paramètres cache, now · Liste des partants confirmés, une ligne par nom et preuves par course.
- [ajouter_noms_pmu](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/rattrapage_historiques.py#L250) · paramètres cache, targets, now · Conserver la graphie PMU si une graphie différente est déjà dans le stock.
- [preparer_noms_passes](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/rattrapage_historiques.py#L268) · paramètres cache, state, now
- [preparer](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/rattrapage_historiques.py#L316) · paramètres cache, now
- [capture](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/rattrapage_historiques.py#L353) · paramètres ident
- [cle_travail_geny](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/rattrapage_historiques.py#L505) · paramètres horse
- [prochaine_tache](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/rattrapage_historiques.py#L516) · paramètres state, now, attempts
- [valider_sync](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/rattrapage_historiques.py#L556) · paramètres state, horse
- [propager_identite](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/rattrapage_historiques.py#L566) · paramètres state, horse · Enregistrer la preuve sur tous les engagements compatibles du même nom.
- [propager_preuve](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/rattrapage_historiques.py#L586) · paramètres state, horse
- [actualiser_cohortes](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/rattrapage_historiques.py#L605) · paramètres cache, state · Relire les clés exactes du lot initial depuis sa première archive.
- [bornes_cohortes](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/rattrapage_historiques.py#L627) · paramètres state
- [bilan_lot_96](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/rattrapage_historiques.py#L647) · paramètres state
- [persister_etat](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/rattrapage_historiques.py#L675) · paramètres cache, state
- [bilan](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/rattrapage_historiques.py#L680) · paramètres state
- [derniere_acquisition_validee](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/rattrapage_historiques.py#L731) · paramètres cache, state
- [rapport](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/rattrapage_historiques.py#L743) · paramètres state, *, cache=None
- [priorite_production](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/rattrapage_historiques.py#L771) · paramètres paths=None · Céder entre deux chevaux si un workflow de production attend le verrou. · retours littéraux PRIORITE_PRODUCTION_EN_ATTENTE, PRIORITE_PRODUCTION_NON_VERIFIABLE
- [synchroniser_kpi](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/rattrapage_historiques.py#L804) · paramètres engine, state, cache
- [suivre_creneau_nocturne](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/rattrapage_historiques.py#L817) · paramètres previous, now, *, reason, pause, progress
- [signaler_alerte_nocturne](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/rattrapage_historiques.py#L851) · paramètres state
- [main](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/rattrapage_historiques.py#L856) · paramètres aucun
- [controle_pmu](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/rattrapage_historiques.py#L886) · paramètres aucun
- [controle_fond](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/rattrapage_historiques.py#L893) · paramètres aucun
- [progression_locale](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/rattrapage_historiques.py#L902) · paramètres state
- [suivre](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/rattrapage_historiques.py#L909) · paramètres state, reason
- [differer](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/rattrapage_historiques.py#L935) · paramètres reason, state
- [checkpoint_identites](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/rattrapage_historiques.py#L1001) · paramètres aucun

### [pmu_geny/recensement_historiques.py](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/recensement_historiques.py)

Imports déclarés · collections, datetime, historiques_incrementaux, liaison_chevaux_v22, pathlib, rattrapage_historiques, re
- [ouvrir](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/recensement_historiques.py#L10) · paramètres cache, jour, hippodrome
- [tache](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/recensement_historiques.py#L46) · paramètres suivi, state, associations, pause, syncs · N'utiliser que le périmètre demandé, y compris pour les reprises Sheets.
- [lignes_associees](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/recensement_historiques.py#L72) · paramètres suivi, associations, key, statut
- [bilan](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/recensement_historiques.py#L77) · paramètres suivi
- [captures_a_rejouer](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/recensement_historiques.py#L86) · paramètres archive, chemin_suivi, suivi, state, associations · Relire uniquement les captures complètes archivées du même passage.

### [pmu_geny/recette_finale_v21.py](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/recette_finale_v21.py)

Imports déclarés · __future__, argparse, audit_generique_hors_ligne, controle_historique, datetime, json, pathlib, reprise_historiques_v21
Point d’entrée __main__ déclaré.
- [read](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/recette_finale_v21.py#L18) · paramètres path
- [main](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/recette_finale_v21.py#L21) · paramètres aucun

### [pmu_geny/reconcilier_identites_sheets.py](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/reconcilier_identites_sheets.py)

Imports déclarés · ., controle_sync_sheets, datetime, hashlib, identites_chevaux, json, liaison_chevaux_v22, moteur_sheets, sync_google_sheets
- [contexte](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/reconcilier_identites_sheets.py#L14) · paramètres row
- [reparer](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/reconcilier_identites_sheets.py#L20) · paramètres engine, *, checkpoint=inc.checkpoint_distant · Aucune fusion de nom seul ; sauvegarde distante avant le batch atomique.

### [pmu_geny/reparer_ferrures.py](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/reparer_ferrures.py)

Imports déclarés · argparse, copy, csv, datetime, ferrures_geny, hashlib, historiques_incrementaux, json, liaison_chevaux_v22, partants_actuels_v21, pathlib, re, urllib.request
Point d’entrée __main__ déclaré.
- [reparer_partants](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/reparer_ferrures.py#L16) · paramètres cache, fetch=None
- [public](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/reparer_ferrures.py#L19) · paramètres url
- [reparer](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/reparer_ferrures.py#L53) · paramètres cache, *, partants=False, fetch=None
- [main](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/reparer_ferrures.py#L82) · paramètres aucun

### [pmu_geny/reprise_historiques_v21.py](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/reprise_historiques_v21.py)

Imports déclarés · __future__, argparse, collecte_geny_v4, controle_historique, csv, datetime, json, pathlib, re, urllib.parse
Point d’entrée __main__ déclaré.
- [read_json](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/reprise_historiques_v21.py#L44) · paramètres path
- [validate_url](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/reprise_historiques_v21.py#L47) · paramètres doc, ident
- [normalize](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/reprise_historiques_v21.py#L55) · paramètres doc, ident
- [audit_sources](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/reprise_historiques_v21.py#L80) · paramètres root
- [import_one](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/reprise_historiques_v21.py#L102) · paramètres cache, ident, doc, apply · retours littéraux CONSERVE_COMPLET_EXISTANT, IMPORTE_COMPLET, IMPORT_PREVU
- [main](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/reprise_historiques_v21.py#L126) · paramètres aucun

### [pmu_geny/resolution_identites_courses.py](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/resolution_identites_courses.py)

Imports déclarés · ., cadence_geny, collecte_geny_v4, collections, datetime, decouverte_partants, echeances_production, historique_individuel, json, liaison_chevaux_v22, pathlib, playwright.sync_api, rattrapage_historiques, re, urllib.parse
- [identifiant_course](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/resolution_identites_courses.py#L20) · paramètres url
- [inventaire](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/resolution_identites_courses.py#L28) · paramètres cache, state · Repartir du contexte PMU et du rapprochement de course déjà contrôlé.
- [lire_page](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/resolution_identites_courses.py#L73) · paramètres course, *, page=None
- [preuves_concordantes](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/resolution_identites_courses.py#L113) · paramètres cache, course, proof, now · Filtrer chaque lien sur le numéro, le nom et les identités déjà prouvées.
- [passage](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/resolution_identites_courses.py#L152) · paramètres cache, state, *, stop_requested, checkpoint, collect=None, now=lambda: datetime.now(inc.UTC) · Traiter au plus une page par passage et suivre une cohorte fixe de dix courses.

### [pmu_geny/resultats_v18.py](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/resultats_v18.py)

Imports déclarés · auto_v18, datetime, echeances_production, json, pathlib
- [classement_podium](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/resultats_v18.py#L6) · paramètres rows · Valider les rangs de compétition PMU, y compris les ex æquo.
- [podium_programme](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/resultats_v18.py#L22) · paramètres course
- [enregistrer_resultats](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/resultats_v18.py#L41) · paramètres cache: Path, course: dict, participants: dict, *, observe=None · retours littéraux ARRIVEE_DEJA_ENREGISTREE, ARRIVEE_ENREGISTREE, ARRIVEE_NON_VERIFIEE

### [pmu_geny/revalider_diagnostics.py](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/revalider_diagnostics.py)

Imports déclarés · ., carriere_geny, collecte_geny_v4, controle_historique, datetime, ferrures_geny, hashlib, json, liaison_chevaux_v22, os, pathlib, re, requests, tempfile, zipfile
- [revalider](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/revalider_diagnostics.py#L19) · paramètres cache, archive
- [read](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/revalider_diagnostics.py#L26) · paramètres name
- [revalider_artifacts](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/revalider_diagnostics.py#L92) · paramètres cache, identifiants · Télécharger uniquement les artefacts du dépôt courant, avec son jeton Actions.

### [pmu_geny/selection_metier_v20_4.py](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/selection_metier_v20_4.py)

Imports déclarés · __future__, re, unicodedata
- [normaliser](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/selection_metier_v20_4.py#L24) · paramètres value
- [normaliser_hippodrome](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/selection_metier_v20_4.py#L29) · paramètres value · Identifiant canonique local : supprime les préfixes PMU sans confondre les sites.
- [discipline_course](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/selection_metier_v20_4.py#L37) · paramètres course, reunion · Priorité au champ propre à la course ; réunion utilisable si unique.
- [allocation_eur](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/selection_metier_v20_4.py#L62) · paramètres course
- [groupe_course](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/selection_metier_v20_4.py#L72) · paramètres course
- [niveau](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/selection_metier_v20_4.py#L80) · paramètres course, reunion, hippodrome, nombre_partants · Retourne (niveau, motif, meta). None => exclusion traçable.

### [pmu_geny/signaux_geny.py](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/signaux_geny.py)

Imports déclarés · collections, datetime, departs_trot, echeances_production, formes_contextuelles_v32, liaison_chevaux_v22, profils_partants, selection_metier_v20_4, statistics, structure_geny
- [signaux](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/signaux_geny.py#L20) · paramètres course, profil, lien, observation
- [ajustement](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/signaux_geny.py#L77) · paramètres features, reference · Écart de forme sur /5 avec rétrécissement, zéro en l'absence de preuve.
- [candidat_classement](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/signaux_geny.py#L85) · paramètres ranking, features · Départage d'observation sur /5, avec l'ordre d'origine pour les ex æquo.

### [pmu_geny/sources_experts_v23.py](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/sources_experts_v23.py)

Imports déclarés · __future__, bs4, datetime, ferrures_geny, hashlib, json, liaison_chevaux_v22, ml_v19, partants_actuels_v21, pathlib, re, urllib.parse, urllib.request, zoneinfo
- [text](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/sources_experts_v23.py#L22) · paramètres node
- [track](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/sources_experts_v23.py#L25) · paramètres value
- [title](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/sources_experts_v23.py#L31) · paramètres value
- [same_race](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/sources_experts_v23.py#L36) · paramètres course, date, hippodrome, name
- [fetch_public](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/sources_experts_v23.py#L41) · paramètres url
- [number](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/sources_experts_v23.py#L51) · paramètres value
- [matched](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/sources_experts_v23.py#L57) · paramètres participants, num, name
- [ferrure_label](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/sources_experts_v23.py#L60) · paramètres value
- [profile_equidia](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/sources_experts_v23.py#L64) · paramètres p
- [parser_equidia](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/sources_experts_v23.py#L75) · paramètres html, course, participants, code=None
- [links](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/sources_experts_v23.py#L126) · paramètres html, pattern
- [parser_zeturf](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/sources_experts_v23.py#L131) · paramètres html, course, participants
- [parser_pmu](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/sources_experts_v23.py#L167) · paramètres prono, course, participants
- [collecter](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/sources_experts_v23.py#L188) · paramètres cache, course, raw, now=None, fetch=None · retours littéraux APRES_DEPART
- [page](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/sources_experts_v23.py#L199) · paramètres url
- [completer_partants](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/sources_experts_v23.py#L258) · paramètres cache, course · Conserver les profils PMU ; retirer les anciens compléments tiers.
- [champs_sheet](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/sources_experts_v23.py#L267) · paramètres experts, n, nom=None · Champs PMU exclusivement ; les anciennes sources tierces sont ignorées.

### [pmu_geny/structure_geny.py](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/structure_geny.py)

Imports déclarés · collections, re
- [est_url](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/structure_geny.py#L14) · paramètres value
- [structurer](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/structure_geny.py#L18) · paramètres texte
- [unique](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/structure_geny.py#L32) · paramètres field, candidates
- [couverture](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/structure_geny.py#L88) · paramètres rows

### [pmu_geny/sync_google_sheets.py](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/sync_google_sheets.py)

Imports déclarés · avis_24h_trot, controle_sync_sheets, cotes_v19, csv, cycle_ml_actif, dashboard.trot_analytics.dates, dashboard.trot_analytics.usages, datetime, departs_trot, echeances_production, hashlib, identites_chevaux, ipr, json, lectures_sheets, liaison_chevaux_v22, moteur_sheets, os, partants_actuels_v21, pathlib, profils_partants, rapprochement_reunions, re, resultats_v18, sources_experts_v23, structure_geny, sys, unicodedata
Point d’entrée __main__ déclaré.
- [sheet_value](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/sync_google_sheets.py#L87) · paramètres field, value · retours littéraux
- [canonical_headers](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/sync_google_sheets.py#L239) · paramètres visible
- [read_csv](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/sync_google_sheets.py#L243) · paramètres path
- [load_json](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/sync_google_sheets.py#L248) · paramètres path
- [colname](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/sync_google_sheets.py#L253) · paramètres n
- [course_info](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/sync_google_sheets.py#L260) · paramètres cache, code, date
- [champs_course_pmu](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/sync_google_sheets.py#L269) · paramètres info
- [course_key](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/sync_google_sheets.py#L288) · paramètres date, hippodrome, code
- [selection_predepart](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/sync_google_sheets.py#L295) · paramètres prediction, departure, now · Numéros du TOP3 enregistré, dans l'ordre de la prévision.
- [matching_pct](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/sync_google_sheets.py#L312) · paramètres prediction, arrival, departure, now=None · Score 0–100, uniquement avec preuves temporelles et podium unique. · retours littéraux
- [conclusion_methodes](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/sync_google_sheets.py#L333) · paramètres scores · Comparer exclusivement les scores temporellement vérifiés, sans faux gagnant. · retours littéraux Aucune prévision indépendante évaluable avant cette arrivée, Échec commun : aucun cheval retrouvé (0/3)
- [source_rows](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/sync_google_sheets.py#L351) · paramètres cache, *, now=None · retours littéraux ML_NON_ENTRAINE, ML_NON_PUBLIE_AVANT_DEPART
- [statut_ml](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/sync_google_sheets.py#L362) · paramètres document, depart · retours littéraux ML_NON_ENTRAINE, ML_NON_PUBLIE_AVANT_DEPART
- [normalize_horse_name](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/sync_google_sheets.py#L373) · paramètres value
- [_eval_podium](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/sync_google_sheets.py#L688) · paramètres doc
- [nom_partant](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/sync_google_sheets.py#L717) · paramètres numero
- [identite_sportive](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/sync_google_sheets.py#L836) · paramètres r · Champs stables d'une performance, independants de sa provenance Geny.
- [qualite_source](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/sync_google_sheets.py#L841) · paramètres value
- [ajouter_performance](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/sync_google_sheets.py#L845) · paramètres ident, r
- [ensure_headers](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/sync_google_sheets.py#L928) · paramètres existing, additions
- [plan_sheet](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/sync_google_sheets.py#L932) · paramètres existing_headers, existing_rows, new_items, tab, now=None · Planning sans mutation: met à jour uniquement les colonnes propriétaires du bridge.
- [rowkey](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/sync_google_sheets.py#L950) · paramètres row
- [reconcilier_cles_historiques](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/sync_google_sheets.py#L1013) · paramètres existing_rows, incoming · Rejouer sous la cle deja publiee si la signature technique a evolue.
- [identity_for](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/sync_google_sheets.py#L1035) · paramètres row
- [limiter_cours_registre](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/sync_google_sheets.py#L1059) · paramètres source, date_debut=LIVE_RESET_DATE · Ne filtre que les onglets operationnels; ne touche jamais aux historiques.
- [lire_feuille_complete](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/sync_google_sheets.py#L1068) · paramètres session, base, tab, properties, page_rows=2000, *, raw_dates=False, render_option='UNFORMATTED_VALUE' · Lire toutes les lignes sans perdre les positions des plages vides.
- [publier_plan](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/sync_google_sheets.py#L1120) · paramètres engine, plan · Publier toutes les obligations du plan et relire les résultats ciblés.
- [main](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/sync_google_sheets.py#L1174) · paramètres aucun

### [pmu_geny/test_correctif_macumba_v16_1.py](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/test_correctif_macumba_v16_1.py)

Imports déclarés · __future__, collecte_geny_v4, controle_historique, json, pathlib, tempfile, traitement_course
Point d’entrée __main__ déclaré.
- [main](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/test_correctif_macumba_v16_1.py#L11) · paramètres aucun

### [pmu_geny/test_diagnostic_v14.py](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/test_diagnostic_v14.py)

Imports déclarés · collecte_geny_v4, controle_historique, json, pathlib
Point d’entrée __main__ déclaré.
- [run_tests](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/test_diagnostic_v14.py#L8) · paramètres aucun

### [pmu_geny/test_parser_v13.py](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/test_parser_v13.py)

Imports déclarés · collecte_geny_v4
Point d’entrée __main__ déclaré.
- [essai](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/test_parser_v13.py#L5) · paramètres aucun

### [pmu_geny/top3_independants_v22.py](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/top3_independants_v22.py)

Imports déclarés · __future__, auto_v18, cotes_v19, datetime, departs_trot, formes_contextuelles_v32, liaison_chevaux_v22, ml_v19, partants_actuels_v21, pathlib, profils_partants, re, signaux_geny
- [_musique](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/top3_independants_v22.py#L16) · paramètres value
- [_form_score](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/top3_independants_v22.py#L34) · paramètres participant
- [calculer](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/top3_independants_v22.py#L43) · paramètres cache, course, raw, now=None, clock=None, *, inclure_cotes=True · Compatibilité des appels existants, avec publication du marché séparée.
- [_calculer_direct](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/top3_independants_v22.py#L54) · paramètres cache, course, raw, now, clock · retours littéraux ANCIEN_RELEVE_PLUS_COMPLET, APRES_DEPART, DONNEES_INSUFFISANTES, PARTANTS_ABSENTS, PARTANTS_INCOHERENTS
- [score_experimental](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/top3_independants_v22.py#L154) · paramètres horse

### [pmu_geny/traitement_course.py](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/traitement_course.py)

Imports déclarés · __future__, argparse, collecte_geny_v4, controle_historique, csv, datetime, extraction_historique_par_cheval, json, pathlib, shutil, time
Point d’entrée __main__ déclaré.
- [_save_bilan](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/traitement_course.py#L21) · paramètres sortie: Path, bilan: dict
- [_lire_etat](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/traitement_course.py#L26) · paramètres path: Path
- [_ecrire_etat](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/traitement_course.py#L34) · paramètres path: Path, obj: dict
- [_revalider_historique_cache](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/traitement_course.py#L41) · paramètres fichier: Path · Reparer uniquement les classements verifiables depuis le CSV/JSON sauvegarde.
- [traiter](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/traitement_course.py#L92) · paramètres manifest: dict, sortie: Path, max_chevaux: int, etat_path: Path &#124; None=None, cooldown_heures: float=0.5
- [main](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/pmu_geny/traitement_course.py#L265) · paramètres aucun

### [scripts/audit_ipr.py](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/scripts/audit_ipr.py)

Imports déclarés · argparse, collections, datetime, pathlib, pmu_geny.echeances_production, pmu_geny.identites_chevaux, pmu_geny.ipr, pmu_geny.ipr_prospectif, pmu_geny.liaison_chevaux_v22, pmu_geny.sync_google_sheets, subprocess, tempfile
Point d’entrée __main__ déclaré.
- [archive](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/scripts/audit_ipr.py#L17) · paramètres root, ref, cache, folders
- [audit](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/scripts/audit_ipr.py#L24) · paramètres root, ref, requested, now

### [scripts/audit_ml_ticket_112.py](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/scripts/audit_ml_ticket_112.py)

Imports déclarés · argparse, collections, pathlib, pmu_geny.cycle_ml_actif, pmu_geny.echeances_production, pmu_geny.experience_ml, pmu_geny.ml_v19, pmu_geny.performance_prospective, pmu_geny.profils_partants
Point d’entrée __main__ déclaré.
- [couverture](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/scripts/audit_ml_ticket_112.py#L32) · paramètres rows
- [rejeu](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/scripts/audit_ml_ticket_112.py#L43) · paramètres rows
- [preuves_appariees](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/scripts/audit_ml_ticket_112.py#L75) · paramètres cache, entries, as_of, *, phase=None
- [audit](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/scripts/audit_ml_ticket_112.py#L131) · paramètres cache, as_of, revision

### [scripts/evaluer_enrichissements_pmu.py](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/scripts/evaluer_enrichissements_pmu.py)

Imports déclarés · argparse, collections, datetime, json, numpy, pathlib, pmu_geny.experience_ml, pmu_geny.ml_v19
Point d’entrée __main__ déclaré.
- [ajouter_ecarts_medians](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/scripts/evaluer_enrichissements_pmu.py#L17) · paramètres rows
- [comparer](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/scripts/evaluer_enrichissements_pmu.py#L37) · paramètres cache, first_test, as_of, published=None

### [scripts/migrer_structure_geny.py](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/scripts/migrer_structure_geny.py)

Imports déclarés · argparse, cryptography.hazmat.primitives, cryptography.hazmat.primitives.asymmetric, cryptography.hazmat.primitives.ciphers.aead, hashlib, json, os, pathlib, pmu_geny.moteur_sheets
Point d’entrée __main__ déclaré.
- [main](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/scripts/migrer_structure_geny.py#L15) · paramètres aucun
- [sauvegarder](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/scripts/migrer_structure_geny.py#L24) · paramètres values

### [scripts/synchroniser_un_historique.py](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/scripts/synchroniser_un_historique.py)

Imports déclarés · pathlib, pmu_geny.moteur_sheets
- [synchroniser](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/scripts/synchroniser_un_historique.py#L7) · paramètres horse, spreadsheet, cache=None

### [scripts/valider_session_geny_hors_ligne.py](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/scripts/valider_session_geny_hors_ligne.py)

Imports déclarés · json, pathlib, playwright.sync_api, pmu_geny.extraction_historique_par_cheval, pmu_geny.historique_individuel, tempfile, unittest.mock
- [route](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/scripts/valider_session_geny_hors_ligne.py#L16) · paramètres r

### [scripts/valider_streamlit_registre.py](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/scripts/valider_streamlit_registre.py)

Imports déclarés · json, os, pathlib, streamlit.testing.v1
Point d’entrée __main__ déclaré.
- [main](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/scripts/valider_streamlit_registre.py#L9) · paramètres aucun

### [tests/test_arrival_recovery_window.py](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_arrival_recovery_window.py)

Imports déclarés · datetime, pmu_geny.planification_v20_2, unittest, zoneinfo
Point d’entrée __main__ déclaré.
- [test_yesterday_is_selected_only_for_arrival_recovery](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_arrival_recovery_window.py#L12) · paramètres self
- [test_old_archives_are_excluded](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_arrival_recovery_window.py#L30) · paramètres self
- [test_archived_result_is_not_reprocessed](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_arrival_recovery_window.py#L39) · paramètres self

### [tests/test_audit_checkpoint_offline.py](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_audit_checkpoint_offline.py)

Imports déclarés · datetime, pmu_geny.audit_checkpoint, unittest
Point d’entrée __main__ déclaré.
- [setUp](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_audit_checkpoint_offline.py#L8) · paramètres self
- [audit](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_audit_checkpoint_offline.py#L23) · paramètres self
- [test_partiel_coherent_ne_signifie_pas_termine](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_audit_checkpoint_offline.py#L26) · paramètres self
- [test_total_incoherent](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_audit_checkpoint_offline.py#L31) · paramètres self
- [test_fausse_fin](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_audit_checkpoint_offline.py#L35) · paramètres self
- [test_fin_avec_compteurs_concordants](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_audit_checkpoint_offline.py#L39) · paramètres self
- [test_lot_96_inchange](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_audit_checkpoint_offline.py#L45) · paramètres self
- [test_lot_96_restantes_calculees_sur_les_publications](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_audit_checkpoint_offline.py#L49) · paramètres self
- [test_lot_96_compteur_negatif_refuse](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_audit_checkpoint_offline.py#L55) · paramètres self
- [test_bilan_perime](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_audit_checkpoint_offline.py#L59) · paramètres self
- [test_bilan_frais_mais_acquisition_ancienne](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_audit_checkpoint_offline.py#L63) · paramètres self
- [test_horodatage_acquisition_absent_invalide_ou_futur](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_audit_checkpoint_offline.py#L70) · paramètres self
- [test_compteur_booleen_refuse](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_audit_checkpoint_offline.py#L81) · paramètres self

### [tests/test_avis_24h_trot_offline.py](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_avis_24h_trot_offline.py)

Imports déclarés · datetime, pathlib, pmu_geny, pmu_geny.echeances_production, tempfile, unittest, unittest.mock
- [test_article_rattache_a_un_seul_prix](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_avis_24h_trot_offline.py#L25) · paramètres self
- [test_collecte_preuve_deduplication_et_limite_depart](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_avis_24h_trot_offline.py#L33) · paramètres self

### [tests/test_cadence_geny_offline.py](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_cadence_geny_offline.py)

Imports déclarés · datetime, pathlib, pmu_geny, pmu_geny.cadence_geny, pmu_geny.historique_individuel, tempfile, types, unittest, unittest.mock
- [setUp](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_cadence_geny_offline.py#L16) · paramètres self
- [test_reservation_survit_a_un_arret_entre_deux_runners](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_cadence_geny_offline.py#L22) · paramètres self
- [test_retry_after_precede_la_reprise_a_60_puis_30](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_cadence_geny_offline.py#L30) · paramètres self
- [test_compte_les_requetes_reelles_et_les_indications_serveur](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_cadence_geny_offline.py#L46) · paramètres self
- [test_deux_files_partagent_la_cadence_et_cedent_a_pmu_avant_nouvel_acces](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_cadence_geny_offline.py#L67) · paramètres self
- [avancer](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_cadence_geny_offline.py#L73) · paramètres secondes
- [collecter](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_cadence_geny_offline.py#L78) · paramètres horse, out
- [premier_choix](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_cadence_geny_offline.py#L83) · paramètres state, now, attempts
- [suivant](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_cadence_geny_offline.py#L86) · paramètres state, now, attempts
- [file_neuve](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_cadence_geny_offline.py#L89) · paramètres *args
- [checkpoint](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_cadence_geny_offline.py#L92) · paramètres cache

### [tests/test_carriere_inedite_offline.py](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_carriere_inedite_offline.py)

Imports déclarés · copy, datetime, json, pmu_geny.carriere_geny, pmu_geny.controle_historique, unittest
- [html](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_carriere_inedite_offline.py#L10) · paramètres data
- [setUp](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_carriere_inedite_offline.py#L16) · paramètres self
- [test_zero_explicitement_prouve_avant_depart_sans_inventer_une_course](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_carriere_inedite_offline.py#L25) · paramètres self
- [test_absence_de_champ_filtre_identite_ou_course_differente_ne_prouvent_pas_zero](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_carriere_inedite_offline.py#L34) · paramètres self
- [test_compteurs_contradictoires_et_capture_apres_depart_restent_incomplets](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_carriere_inedite_offline.py#L47) · paramètres self

### [tests/test_chronos_comparables_offline.py](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_chronos_comparables_offline.py)

Imports déclarés · pmu_geny.formes_contextuelles_v32, unittest
- [test_ne_retenient_que_les_sorties_proches_et_anterieures](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_chronos_comparables_offline.py#L7) · paramètres self

### [tests/test_cotes_diagnostic_offline.py](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_cotes_diagnostic_offline.py)

Imports déclarés · datetime, pathlib, pmu_geny.cotes_v19, tempfile, unittest
- [test_champ_absent_et_rapport_rejete_sont_distincts](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_cotes_diagnostic_offline.py#L10) · paramètres self

### [tests/test_cotes_pmu_offline.py](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_cotes_pmu_offline.py)

Imports déclarés · datetime, pathlib, pmu_geny.auto_v18, pmu_geny.cotes_v19, pmu_geny.kpi_registre, pmu_geny.sync_google_sheets, tempfile, unittest, unittest.mock
- [setUp](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_cotes_pmu_offline.py#L15) · paramètres self
- [participant](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_cotes_pmu_offline.py#L28) · paramètres self, num, cote=None, *, statut='PARTANT', report=None
- [relever](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_cotes_pmu_offline.py#L37) · paramètres self, rows, now=None
- [test_cycle_global_prepare_toutes_les_courses_attendues_de_la_reunion](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_cotes_pmu_offline.py#L40) · paramètres self
- [test_cache_partiel_conserve_les_cotes_et_leurs_dates](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_cotes_pmu_offline.py#L59) · paramètres self
- [test_rapport_futur_ou_ancien_et_retrait](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_cotes_pmu_offline.py#L74) · paramètres self
- [test_source_sheets_independante_et_top3_partiel](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_cotes_pmu_offline.py#L95) · paramètres self
- [test_un_appel_participants_et_publication_malgre_un_echec_enrichissement](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_cotes_pmu_offline.py#L118) · paramètres self

### [tests/test_cycle_experimental_automatique_offline.py](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_cycle_experimental_automatique_offline.py)

Imports déclarés · datetime, pathlib, pmu_geny.cycle_ml_experimental, tempfile, unittest, unittest.mock
- [test_demarre_sous_le_seuil_de_production_et_ne_promeut_pas](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_cycle_experimental_automatique_offline.py#L8) · paramètres self

### [tests/test_departs_trot_offline.py](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_departs_trot_offline.py)

Imports déclarés · datetime, pathlib, pmu_geny.auto_v18, pmu_geny.departs_trot, pmu_geny.ferrures_geny, pmu_geny.formes_contextuelles_v32, pmu_geny.ml_v19, pmu_geny.partants_actuels_v21, pmu_geny.sync_google_sheets, tempfile, unittest, unittest.mock
- [setUp](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_departs_trot_offline.py#L16) · paramètres self
- [test_position_sourcee_capacites_et_absences](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_departs_trot_offline.py#L25) · paramètres self
- [test_non_partant_et_depart_volte_distinct_de_l_inconnu](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_departs_trot_offline.py#L39) · paramètres self
- [test_relecture_apres_depart_ne_remplace_pas_la_position_capturee](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_departs_trot_offline.py#L52) · paramètres self
- [test_historique_geny_explicite_sans_fuite_temporelle](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_departs_trot_offline.py#L73) · paramètres self
- [test_ml_capture_les_champs_candidats_sans_cotes](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_departs_trot_offline.py#L90) · paramètres self

### [tests/test_echeances_production_offline.py](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_echeances_production_offline.py)

Imports déclarés · datetime, hashlib, json, pathlib, pmu_geny, pmu_geny.kpi_registre, tempfile, unittest, unittest.mock, yaml
Point d’entrée __main__ déclaré.
- [setUp](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_echeances_production_offline.py#L12) · paramètres self
- [mark_global](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_echeances_production_offline.py#L25) · paramètres self, now
- [mark_preparation](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_echeances_production_offline.py#L28) · paramètres self, now
- [predictions](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_echeances_production_offline.py#L34) · paramètres self, now, ml=True
- [publish](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_echeances_production_offline.py#L46) · paramètres self, now, plan=None, *, observation=None
- [test_tick_leger_puis_cycle_global_horaire](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_echeances_production_offline.py#L59) · paramètres self
- [test_collecte_ne_charge_pas_navigateur_pendant_pause_sauf_publication_a_reprendre](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_echeances_production_offline.py#L64) · paramètres self
- [test_pause_commune_active_et_expiree_sur_un_creneau_nocturne](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_echeances_production_offline.py#L75) · paramètres self
- [test_echeance_commune_la_plus_tardive_reste_active](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_echeances_production_offline.py#L98) · paramètres self
- [test_relais_apres_preparation_sans_relacher_garde_arrivees](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_echeances_production_offline.py#L107) · paramètres self
- [test_global_perime_ne_bloque_pas_la_nuit_mais_reprend_a_7h](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_echeances_production_offline.py#L127) · paramètres self
- [test_21h_ne_declenche_que_la_preparation_manquante](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_echeances_production_offline.py#L140) · paramètres self
- [test_creneau_nocturne_suit_paris_ete_hiver_et_garde_la_marge](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_echeances_production_offline.py#L151) · paramètres self
- [test_budget_nocturne_franchit_minuit_et_reserve_les_arrivees](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_echeances_production_offline.py#L165) · paramètres self
- [test_relecture_sheets_justifie_la_version_avant_depart](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_echeances_production_offline.py#L177) · paramètres self
- [test_h3_reserve_trente_minutes_et_reste_du_si_non_publie](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_echeances_production_offline.py#L200) · paramètres self
- [test_anticipation_55_minutes_sans_relacher_la_fraicheur](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_echeances_production_offline.py#L208) · paramètres self
- [test_retard_atteste_ne_reinitialise_pas_indefiniment_le_global](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_echeances_production_offline.py#L219) · paramètres self
- [test_publication_reussie_gel_immuable_puis_h2](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_echeances_production_offline.py#L231) · paramètres self
- [test_tick_manquant_et_echeances_concurrentes](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_echeances_production_offline.py#L250) · paramètres self
- [test_ancien_h2_reste_h2_et_ancien_h1_reste_immuable](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_echeances_production_offline.py#L268) · paramètres self
- [test_echec_sheets_ne_certifie_ni_jalon_ni_cycle_global](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_echeances_production_offline.py#L294) · paramètres self
- [test_h3_incomplet_reessaie_sans_reecrire_les_copies](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_echeances_production_offline.py#L303) · paramètres self
- [test_horodatage_calcul_avant_deadline_ne_masque_pas_publication_tardive](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_echeances_production_offline.py#L316) · paramètres self
- [test_relecture_future_ne_certifie_pas_une_publication](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_echeances_production_offline.py#L324) · paramètres self
- [test_pas_de_certificat_predepart_retroactif](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_echeances_production_offline.py#L332) · paramètres self
- [test_np_et_ml_futur_ou_course_etrangere_invalident_le_controle](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_echeances_production_offline.py#L338) · paramètres self
- [test_cycle_global_non_valide_sur_programme_ancien](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_echeances_production_offline.py#L353) · paramètres self
- [test_cycle_cible_ne_recertifie_pas_les_courses_non_rafraichies](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_echeances_production_offline.py#L359) · paramètres self
- [test_reunion_complete_et_lecture_ponctuelle_avant_certification](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_echeances_production_offline.py#L370) · paramètres self
- [test_trois_ecrivains_file_max_et_unique_verrou](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_echeances_production_offline.py#L396) · paramètres self
- [test_cli_fait_echouer_un_controle_fonctionnel_non_publie](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_echeances_production_offline.py#L410) · paramètres self
- [test_depart_pmu_reporte_ne_fait_pas_echouer_certification](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_echeances_production_offline.py#L420) · paramètres self

### [tests/test_experience_ml_offline.py](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_experience_ml_offline.py)

Imports déclarés · datetime, hashlib, pathlib, pmu_geny.experience_ml, pmu_geny.ml_v19, tempfile, unittest, unittest.mock
Point d’entrée __main__ déclaré.
- [test_calendar_split_holds_out_whole_courses](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_experience_ml_offline.py#L16) · paramètres self
- [test_top3_counts_by_race_and_breaks_ties_by_number](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_experience_ml_offline.py#L25) · paramètres self
- [test_profils_direct_isoles_sur_la_prevision_certifiee](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_experience_ml_offline.py#L32) · paramètres self
- [test_profils_ml_test_hors_apprentissage_et_valeurs_manquantes](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_experience_ml_offline.py#L62) · paramètres self
- [test_snapshot_preserves_horse_name_and_immutability](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_experience_ml_offline.py#L73) · paramètres self

### [tests/test_ferrures_offline.py](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_ferrures_offline.py)

Imports déclarés · copy, datetime, json, os, pathlib, pmu_geny, pmu_geny.moteur_sheets, pmu_geny.partants_actuels_v21, pmu_geny.reparer_ferrures, pmu_geny.sync_google_sheets, tempfile, test_v26_chaine_offline, test_v26_incremental_offline, unittest, unittest.mock, urllib.error
Point d’entrée __main__ déclaré.
- [participation](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_ferrures_offline.py#L23) · paramètres code='FF', *, ident='123456', date='2026-01-01', rank=3, chrono="1'15''0", pid=1
- [html](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_ferrures_offline.py#L29) · paramètres records=(), *, dom='', ident='123456'
- [perf](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_ferrures_offline.py#L35) · paramètres date='2026-01-01', rank='3', chrono="1'15''0"
- [pmu](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_ferrures_offline.py#L40) · paramètres name='Test', **extra
- [test_texte_petite_piste_et_nom_driver_ne_sont_pas_des_ferrures](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_ferrures_offline.py#L46) · paramètres self
- [test_nettoyage_limite_aux_anciens_faux_codes_dont_le_texte_est_identique](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_ferrures_offline.py#L54) · paramètres self
- [setUp](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_ferrures_offline.py#L67) · paramètres self
- [test_pmu_trot_sans_declaration_est_ferre_avec_provenance](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_ferrures_offline.py#L71) · paramètres self
- [test_absence_generique_galop_et_code_inconnu_ne_deviennent_pas_ferre](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_ferrures_offline.py#L77) · paramètres self
- [test_enregistrement_pmu_conserve_url_et_heure_de_la_source](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_ferrures_offline.py#L81) · paramètres self
- [test_codes_geny_distincts_des_codes_pmu_et_libelles_accessibles](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_ferrures_offline.py#L88) · paramètres self
- [test_structure_source_enrichit_la_bonne_performance_sans_changer_son_texte](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_ferrures_offline.py#L95) · paramètres self
- [test_pictogramme_dom_charge_apres_bloc_initial_est_lu](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_ferrures_offline.py#L102) · paramètres self
- [test_identite_ou_date_differente_et_valeur_absente_ne_sont_pas_inventees](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_ferrures_offline.py#L112) · paramètres self
- [test_deux_courses_meme_jour_sont_departagees_par_rang_et_chrono](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_ferrures_offline.py#L119) · paramètres self
- [seed_capture](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_ferrures_offline.py#L128) · paramètres self, *, ferrure=None
- [report](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_ferrures_offline.py#L136) · paramètres self, *, ferrure=None
- [test_ajout_de_ferrure_ne_provoque_pas_une_fausse_regression](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_ferrures_offline.py#L144) · paramètres self
- [test_ferrure_connue_est_conservee_et_une_contradiction_bloque](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_ferrures_offline.py#L152) · paramètres self
- [test_reparation_archive_reproductible_et_date_de_capture_intacte](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_ferrures_offline.py#L159) · paramètres self
- [test_reparation_pmu_ne_modifie_que_le_champ_ferrure_de_la_bonne_identite](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_ferrures_offline.py#L170) · paramètres self
- [test_archive_de_depart_persistante_sans_nouvelle_ferrure](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_ferrures_offline.py#L184) · paramètres self
- [test_carriere_complete_sans_ferrures_reste_a_completer](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_ferrures_offline.py#L207) · paramètres self
- [test_reparation_pmu_respecte_un_refus_429_sans_poursuite](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_ferrures_offline.py#L217) · paramètres self
- [denied](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_ferrures_offline.py#L222) · paramètres url
- [test_ecriture_ferrure_sur_cle_existante_sans_ajout_ni_effet_sur_previsions](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_ferrures_offline.py#L226) · paramètres self

### [tests/test_historique_kpi_offline.py](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_historique_kpi_offline.py)

Imports déclarés · datetime, json, pmu_geny.historique_kpi, pmu_geny.moteur_sheets, test_v26_chaine_offline, unittest
- [setUp](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_historique_kpi_offline.py#L9) · paramètres self
- [materialiser](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_historique_kpi_offline.py#L13) · paramètres self, updates
- [test_zero_vide_et_total_conserves_sans_inventer_jour_passe](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_historique_kpi_offline.py#L16) · paramètres self
- [test_un_releve_par_jour_actualise_sans_doublon_puis_jour_precedent_gele](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_historique_kpi_offline.py#L24) · paramètres self
- [test_ancienne_echeance_reste_dans_son_releve_et_ne_reapparait_pas](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_historique_kpi_offline.py#L33) · paramètres self
- [test_date_observation_paris_et_non_date_utc](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_historique_kpi_offline.py#L46) · paramètres self
- [test_doublons_et_rejeu_anterieur_refuses](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_historique_kpi_offline.py#L51) · paramètres self
- [test_creation_et_reprise_reelle_sous_moteur_unique](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_historique_kpi_offline.py#L56) · paramètres self
- [post](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_historique_kpi_offline.py#L58) · paramètres self, url, **kwargs

### [tests/test_identification_geny_offline.py](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_identification_geny_offline.py)

Imports déclarés · datetime, json, pathlib, pmu_geny, pmu_geny.historique_individuel, pmu_geny.liaison_chevaux_v22, subprocess, tempfile, unittest, unittest.mock
- [setUp](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_identification_geny_offline.py#L16) · paramètres self
- [test_manifest_without_career_identifies_existing_engagements](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_identification_geny_offline.py#L24) · paramètres self
- [test_identity_is_persisted_and_shared_when_career_request_gets_429](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_identification_geny_offline.py#L46) · paramètres self
- [collect](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_identification_geny_offline.py#L53) · paramètres horse, out
- [test_timeout_after_identification_keeps_published_proof](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_identification_geny_offline.py#L70) · paramètres self
- [collect](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_identification_geny_offline.py#L77) · paramètres horse, out
- [test_retry_is_shared_across_engagements_of_one_confirmed_id](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_identification_geny_offline.py#L94) · paramètres self
- [test_country_suffix_requires_geny_nationality](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_identification_geny_offline.py#L110) · paramètres self
- [test_geny_search_checks_exact_query_and_keeps_homonyms](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_identification_geny_offline.py#L120) · paramètres self

### [tests/test_identites_sources_offline.py](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_identites_sources_offline.py)

Imports déclarés · copy, datetime, json, os, pathlib, pmu_geny, pmu_geny.identites_chevaux, pmu_geny.moteur_sheets, pmu_geny.reconcilier_identites_sheets, pmu_geny.sync_google_sheets, tempfile, test_v26_chaine_offline, test_v26_incremental_offline, unittest, unittest.mock
Point d’entrée __main__ déclaré.
- [setUp](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_identites_sources_offline.py#L20) · paramètres self
- [rows](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_identites_sources_offline.py#L37) · paramètres self
- [test_sources_distinctes_et_hotes_exactement_controles](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_identites_sources_offline.py#L55) · paramètres self
- [test_correspondance_exige_le_nom_et_la_source](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_identites_sources_offline.py#L61) · paramètres self
- [test_autre_numero_externe_ne_devient_jamais_un_candidat_geny](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_identites_sources_offline.py#L69) · paramètres self
- [test_migration_conserve_la_cible_figee_et_priorise_la_reprise](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_identites_sources_offline.py#L78) · paramètres self
- [test_ancienne_file_externe_non_reconciliee_est_bloquee](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_identites_sources_offline.py#L95) · paramètres self
- [test_reconciliation_conserve_les_deux_cles_et_ne_mutile_pas_les_entrees](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_identites_sources_offline.py#L106) · paramètres self
- [test_publication_commune_ajoute_seulement_le_manquant_et_rejoue_sans_doublon](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_identites_sources_offline.py#L114) · paramètres self
- [test_desaccord_chrono_ou_ferrure_bloque_avant_toute_ecriture](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_identites_sources_offline.py#L127) · paramètres self
- [test_le_controle_identifiant_geny_reste_bloquant](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_identites_sources_offline.py#L138) · paramètres self
- [test_doublon_preexistant_entre_sources_bloque_dans_les_deux_ordres](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_identites_sources_offline.py#L143) · paramètres self
- [test_ancien_id_avec_url_geny_deja_corrigee_est_aussi_reconcilie](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_identites_sources_offline.py#L150) · paramètres self
- [repair_case](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_identites_sources_offline.py#L155) · paramètres self
- [post](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_identites_sources_offline.py#L167) · paramètres self, url, **kwargs
- [test_reparation_sauvegarde_distante_avant_suppression_et_rejoue_sans_perte](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_identites_sources_offline.py#L185) · paramètres self
- [checkpoint](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_identites_sources_offline.py#L188) · paramètres cache
- [test_echec_sauvegarde_interdit_toute_suppression](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_identites_sources_offline.py#L203) · paramètres self
- [test_reparation_refuse_un_changement_de_distance](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_identites_sources_offline.py#L211) · paramètres self
- [test_snapshot_conserve_la_source_necessaire_a_la_reconciliation](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_identites_sources_offline.py#L221) · paramètres self

### [tests/test_index_geny_apres_publication.py](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_index_geny_apres_publication.py)

Imports déclarés · datetime, json, pathlib, pmu_geny.index_geny_apres_publication, tempfile, unittest
- [setUp](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_index_geny_apres_publication.py#L11) · paramètres self
- [save](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_index_geny_apres_publication.py#L21) · paramètres self, name, value
- [test_index_only_on_global](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_index_geny_apres_publication.py#L26) · paramètres self
- [test_fresh_cache](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_index_geny_apres_publication.py#L31) · paramètres self
- [test_shared_pause](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_index_geny_apres_publication.py#L36) · paramètres self
- [test_stop_on_first_refusal](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_index_geny_apres_publication.py#L41) · paramètres self
- [fetch](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_index_geny_apres_publication.py#L43) · paramètres cache, date, state
- [test_workflow_order](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_index_geny_apres_publication.py#L49) · paramètres self

### [tests/test_ipr_offline.py](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_ipr_offline.py)

Imports déclarés · dashboard.trot_analytics.usages, datetime, os, pathlib, pmu_geny.echeances_production, pmu_geny.ipr, pmu_geny.ipr_prospectif, pmu_geny.moteur_sheets, pmu_geny.sync_google_sheets, re, tempfile, test_v26_chaine_offline, unittest, unittest.mock
- [lien](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_ipr_offline.py#L28) · paramètres *rows, stamp=STAMP
- [ligne](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_ipr_offline.py#L34) · paramètres n, **fields
- [test_score_relatif_dai_et_absences](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_ipr_offline.py#L39) · paramètres self
- [test_np_inconnus_et_preparation_interdisent_le_top3](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_ipr_offline.py#L61) · paramètres self
- [test_version_immuable_et_hors_coupure](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_ipr_offline.py#L80) · paramètres self
- [test_certificat_exige_les_valeurs_relues_avant_depart](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_ipr_offline.py#L95) · paramètres self
- [__init__](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_ipr_offline.py#L123) · paramètres self, headers
- [get](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_ipr_offline.py#L129) · paramètres self, url, **kwargs
- [post](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_ipr_offline.py#L157) · paramètres self, url, **kwargs
- [test_migration_a_droite_style_durable_et_zero_distinct_du_vide](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_ipr_offline.py#L175) · paramètres self
- [sync](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_ipr_offline.py#L183) · paramètres source

### [tests/test_kpi_reference_offline.py](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_kpi_reference_offline.py)

Imports déclarés · datetime, pathlib, pmu_geny.kpi_registre, pmu_geny.ml_v19, pmu_geny.moteur_sheets, pmu_geny.sync_google_sheets, re, tempfile, test_v26_chaine_offline, unittest
- [test_maturity_metrics_are_re_read_without_duplicate_append](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_kpi_reference_offline.py#L8) · paramètres self
- [test_kpi_agrandit_une_grille_pleine_avant_publication](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_kpi_reference_offline.py#L32) · paramètres self
- [get](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_kpi_reference_offline.py#L40) · paramètres self, url, **kwargs
- [post](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_kpi_reference_offline.py#L49) · paramètres self, url, **kwargs
- [test_j_j1_emploient_les_lignes_relues_et_exigent_la_provenance_du_f](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_kpi_reference_offline.py#L71) · paramètres self
- [test_ml_counts_and_denominators_same_snapshot](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_kpi_reference_offline.py#L88) · paramètres self
- [test_repair_stale_denominator_even_when_value_unchanged](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_kpi_reference_offline.py#L107) · paramètres self
- [test_inconnus_et_formules_preserves](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_kpi_reference_offline.py#L118) · paramètres self
- [test_workflow_kpi_after_certification](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_kpi_reference_offline.py#L123) · paramètres self

### [tests/test_liens_geny_course_offline.py](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_liens_geny_course_offline.py)

Imports déclarés · datetime, json, pathlib, pmu_geny, pmu_geny.historique_individuel, tempfile, unittest, unittest.mock
Point d’entrée __main__ déclaré.
- [setUp](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_liens_geny_course_offline.py#L11) · paramètres self
- [rows](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_liens_geny_course_offline.py#L18) · paramètres self
- [extraire](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_liens_geny_course_offline.py#L23) · paramètres self, rows=None, html=''
- [memoriser](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_liens_geny_course_offline.py#L26) · paramètres self, proof
- [test_un_tableau_deja_charge_resout_deux_chevaux_sans_ouvrir_leurs_fiches](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_liens_geny_course_offline.py#L30) · paramètres self
- [test_sans_href_retour_possible_aux_donnees_structurees_de_la_meme_course](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_liens_geny_course_offline.py#L37) · paramètres self
- [test_flight_text_before_partants_is_read_without_table_or_click](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_liens_geny_course_offline.py#L48) · paramètres self
- [test_missing_course_link_tries_search_but_access_refusal_does_not](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_liens_geny_course_offline.py#L78) · paramètres self
- [test_nom_numero_course_et_fraicheur_obligatoires_pour_reutiliser](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_liens_geny_course_offline.py#L96) · paramètres self
- [test_noms_ambigus_et_liens_externes_ne_sont_pas_memorises](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_liens_geny_course_offline.py#L106) · paramètres self
- [test_relecture_partielle_conserve_les_autres_liens](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_liens_geny_course_offline.py#L114) · paramètres self
- [test_alimentation_reutilise_identite_sans_promouvoir_carriere](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_liens_geny_course_offline.py#L123) · paramètres self

### [tests/test_matching_direct_ml_offline.py](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_matching_direct_ml_offline.py)

Imports déclarés · datetime, pathlib, pmu_geny.ml_v19, pmu_geny.sync_google_sheets, tempfile, unittest
- [setUp](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_matching_direct_ml_offline.py#L9) · paramètres self
- [pred](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_matching_direct_ml_offline.py#L14) · paramètres self, nums
- [test_four_scores](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_matching_direct_ml_offline.py#L16) · paramètres self
- [test_invalid_or_missing_proofs](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_matching_direct_ml_offline.py#L19) · paramètres self
- [test_invalid_podium_and_invalid_chronology](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_matching_direct_ml_offline.py#L24) · paramètres self
- [test_conclusions_ne_designent_pas_de_faux_gagnant](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_matching_direct_ml_offline.py#L28) · paramètres self
- [test_numeric_values_and_clear](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_matching_direct_ml_offline.py#L35) · paramètres self
- [test_rapprochement_sans_paire_conserve_le_direct_verifie](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_matching_direct_ml_offline.py#L42) · paramètres self
- [test_source_publie_matching_distinct_sur_une_arrivee_verifiee](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_matching_direct_ml_offline.py#L68) · paramètres self

### [tests/test_ml_actif_offline.py](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_ml_actif_offline.py)

Imports déclarés · datetime, hashlib, joblib, json, pathlib, pmu_geny, pmu_geny.cycle_ml_actif, pmu_geny.kpi_registre, pmu_geny.ml_v19, pmu_geny.preparation_prochaines, pmu_geny.top3_independants_v22, tempfile, unittest, unittest.mock
- [setUp](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_ml_actif_offline.py#L16) · paramètres self
- [exemple](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_ml_actif_offline.py#L24) · paramètres self, day='2026-11-16'
- [test_entraine_meme_une_seule_periode_et_predit_sans_promotion](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_ml_actif_offline.py#L33) · paramètres self
- [test_enrichissement_apprend_une_valeur_documentee_et_signale_les_absences](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_ml_actif_offline.py#L49) · paramètres self
- [test_pas_de_reentrainement_pour_des_captures_non_encore_etiquetees](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_ml_actif_offline.py#L65) · paramètres self
- [test_aucun_modele_si_les_arrivees_sont_futures_ou_les_variables_absentes](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_ml_actif_offline.py#L73) · paramètres self
- [test_modele_trafique_et_inference_retroactive_sont_refuses](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_ml_actif_offline.py#L85) · paramètres self
- [test_modele_corrompu_est_reentraine_et_non_reutilise](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_ml_actif_offline.py#L95) · paramètres self
- [test_depart_franchi_durant_le_calcul_ne_produit_aucune_prevision](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_ml_actif_offline.py#L101) · paramètres self
- [test_kpi_rend_visible_le_fit_et_n_ajoute_les_lignes_qu_une_fois](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_ml_actif_offline.py#L111) · paramètres self
- [test_cycle_de_nuit_prepare_top3_et_debloque_les_historiques_du_jour](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_ml_actif_offline.py#L121) · paramètres self

### [tests/test_ml_production_offline.py](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_ml_production_offline.py)

Imports déclarés · datetime, joblib, numpy, pathlib, pmu_geny, pmu_geny.auto_v18, pmu_geny.cycle_ml_actif, pmu_geny.echeances_production, pmu_geny.maturite_ml, pmu_geny.ml_v19, pmu_geny.top3_independants_v22, tempfile, unittest, unittest.mock
Point d’entrée __main__ déclaré.
- [predict_proba](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_ml_production_offline.py#L17) · paramètres self, vectors
- [setUp](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_ml_production_offline.py#L25) · paramètres self
- [model](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_ml_production_offline.py#L36) · paramètres self, **extra
- [examples](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_ml_production_offline.py#L44) · paramètres self
- [test_capture_and_inference_use_same_profiles_without_geny](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_ml_production_offline.py#L56) · paramètres self
- [test_experimental_or_obsolete_models_are_never_used](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_ml_production_offline.py#L79) · paramètres self
- [test_existing_experimental_model_serves_during_schema_transition](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_ml_production_offline.py#L85) · paramètres self
- [test_live_gates_and_unknown_np](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_ml_production_offline.py#L103) · paramètres self
- [test_premier_calcul_ml_possible_des_le_debut_du_jour](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_ml_production_offline.py#L112) · paramètres self
- [test_dataset_rejects_future_labels_missing_podium_and_unknown_np](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_ml_production_offline.py#L117) · paramètres self
- [test_malformed_records_do_not_abort_the_batch](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_ml_production_offline.py#L128) · paramètres self
- [test_connections_use_only_prior_labels_and_same_discipline](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_ml_production_offline.py#L134) · paramètres self
- [prospective_candidate](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_ml_production_offline.py#L149) · paramètres self
- [test_candidate_waits_for_prospective_evidence](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_ml_production_offline.py#L169) · paramètres self
- [test_prospective_decision_keeps_or_promotes_exact_candidate](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_ml_production_offline.py#L179) · paramètres self
- [test_shadow_requires_same_observation_and_a_certified_predeparture_publication](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_ml_production_offline.py#L199) · paramètres self
- [test_production_thresholds_are_not_lowered](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_ml_production_offline.py#L236) · paramètres self
- [test_direct_failure_does_not_block_pmu_ml_capture](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_ml_production_offline.py#L244) · paramètres self
- [test_delayed_cron_and_dataset_fingerprint](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_ml_production_offline.py#L261) · paramètres self
- [test_timezone_summer_winter_and_force_preserves_training_gate](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_ml_production_offline.py#L272) · paramètres self
- [test_failed_attempt_can_resume](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_ml_production_offline.py#L283) · paramètres self

### [tests/test_performance_prospective_offline.py](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_performance_prospective_offline.py)

Imports déclarés · datetime, hashlib, pathlib, pmu_geny.echeances_production, pmu_geny.partants_actuels_v21, pmu_geny.performance_prospective, tempfile, unittest
Point d’entrée __main__ déclaré.
- [setUp](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_performance_prospective_offline.py#L12) · paramètres self
- [test_score_apparie_publie_pas_score_entrainement](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_performance_prospective_offline.py#L29) · paramètres self
- [test_hash_corrompu_et_publication_apres_depart_exclus](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_performance_prospective_offline.py#L34) · paramètres self
- [test_version_archivee_retrouvee_sans_utiliser_nouveau_calcul_non_publie](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_performance_prospective_offline.py#L43) · paramètres self
- [test_depart_apparie_au_direct_sans_publication_ml](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_performance_prospective_offline.py#L49) · paramètres self
- [test_ferrure_inconnue_reste_vide_et_convention_est_distincte](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_performance_prospective_offline.py#L74) · paramètres self
- [test_report_de_depart_ne_melange_pas_les_horaires_des_attestations](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_performance_prospective_offline.py#L82) · paramètres self

### [tests/test_persistance_production_offline.py](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_persistance_production_offline.py)

Imports déclarés · pathlib, pmu_geny.persistance_production, subprocess, tempfile, unittest, unittest.mock
Point d’entrée __main__ déclaré.
- [setUp](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_persistance_production_offline.py#L10) · paramètres self
- [git](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_persistance_production_offline.py#L21) · paramètres self, *args
- [test_sauvegarde_jalons_sans_effacer_donnees_existantes_ni_modifier_code](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_persistance_production_offline.py#L24) · paramètres self
- [test_conflit_distant_arrete_la_sauvegarde_sans_force_push](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_persistance_production_offline.py#L33) · paramètres self
- [concurrent](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_persistance_production_offline.py#L36) · paramètres cmd, *args, **kwargs

### [tests/test_plan_retrait_resultats_offline.py](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_plan_retrait_resultats_offline.py)

Imports déclarés · pmu_geny.plan_retrait_resultats, pmu_geny.sync_google_sheets, unittest, unittest.mock
- [test_retrait_scope_idempotence_et_conservation](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_plan_retrait_resultats_offline.py#L7) · paramètres self
- [test_refus_ambiguite_sur_cle](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_plan_retrait_resultats_offline.py#L21) · paramètres self
- [test_migration_relecture_idempotente_et_sauvegarde_avant_ecriture](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_plan_retrait_resultats_offline.py#L25) · paramètres self
- [test_migration_refuse_modification_concurrente](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_plan_retrait_resultats_offline.py#L47) · paramètres self
- [test_publication_ne_recree_pas_les_colonnes_retirees](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_plan_retrait_resultats_offline.py#L60) · paramètres self

### [tests/test_preparation_prochaines_offline.py](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_preparation_prochaines_offline.py)

Imports déclarés · datetime, os, pathlib, pmu_geny, pmu_geny.preparation_prochaines, pmu_geny.rattrapage_historiques, tempfile, test_v26_incremental_offline, unittest, unittest.mock
- [setUp](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_preparation_prochaines_offline.py#L8) · paramètres self
- [course](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_preparation_prochaines_offline.py#L16) · paramètres self, code, depart, nom='Future'
- [state](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_preparation_prochaines_offline.py#L29) · paramètres self, engagement, key
- [test_cheval_encore_a_courir_avant_tous_les_anciens](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_preparation_prochaines_offline.py#L35) · paramètres self
- [test_nuit_jour_seulement_dans_l_ordre_des_departs_sans_top3](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_preparation_prochaines_offline.py#L43) · paramètres self
- [test_course_deja_partie_exclue_meme_si_jour_identique](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_preparation_prochaines_offline.py#L69) · paramètres self
- [test_prochain_engagement_le_plus_proche_pour_un_id_unique](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_preparation_prochaines_offline.py#L74) · paramètres self
- [test_fond_utilise_attente_locale_puis_cede_des_reessai_possible](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_preparation_prochaines_offline.py#L82) · paramètres self
- [test_creneau_borne_respecte_le_jalon_et_la_cadence](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_preparation_prochaines_offline.py#L94) · paramètres self
- [attente](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_preparation_prochaines_offline.py#L107) · paramètres self, minutes=360
- [test_attente_jour_ne_masque_pas_un_partant_disponible_demain](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_preparation_prochaines_offline.py#L114) · paramètres self
- [test_reprise_prioritaire_imminente_garde_le_creneau](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_preparation_prochaines_offline.py#L121) · paramètres self
- [test_pause_globale_respectee_depuis_journal_et_les_deux_files](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_preparation_prochaines_offline.py#L128) · paramètres self
- [test_publication_en_attente_bloque_meme_si_delai_sync_non_ecoule](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_preparation_prochaines_offline.py#L148) · paramètres self
- [test_attente_locale_ne_masque_pas_profil_perime_ou_prevision_absente](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_preparation_prochaines_offline.py#L154) · paramètres self
- [test_observation_du_creneau_ne_modifie_aucun_fichier_source](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_preparation_prochaines_offline.py#L164) · paramètres self
- [test_absence_prevision_ne_bloque_pas_enrichissement_des_partants_prepares](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_preparation_prochaines_offline.py#L171) · paramètres self
- [test_collecte_possible_si_ferrure_absente_avec_identite_pmu](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_preparation_prochaines_offline.py#L180) · paramètres self
- [test_collecte_interdite_si_profil_pmu_perime](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_preparation_prochaines_offline.py#L188) · paramètres self
- [test_fond_autorise_quand_preparation_et_historique_complets](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_preparation_prochaines_offline.py#L195) · paramètres self
- [test_fond_differe_avant_toute_lecture_sheets](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_preparation_prochaines_offline.py#L206) · paramètres self
- [test_publication_locale_autorisee_quand_geny_est_en_pause](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_preparation_prochaines_offline.py#L224) · paramètres self
- [test_alerte_consecutive_ignore_priorite_pmu_pause_et_double_creneau](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_preparation_prochaines_offline.py#L247) · paramètres self
- [observe](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_preparation_prochaines_offline.py#L251) · paramètres previous, minutes, *, reason='BUDGET_TEMPS_ATTEINT', pause=None, progress=False

### [tests/test_priorite_nocturne_offline.py](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_priorite_nocturne_offline.py)

Imports déclarés · copy, datetime, pathlib, pmu_geny, tempfile, unittest, unittest.mock, zoneinfo
Point d’entrée __main__ déclaré.
- [setUp](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_priorite_nocturne_offline.py#L15) · paramètres self
- [horse](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_priorite_nocturne_offline.py#L19) · paramètres self, engagement, *, missing=True, known=False
- [test_nuit_paris_et_changements_d_heure](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_priorite_nocturne_offline.py#L26) · paramètres self
- [test_production_nuit_partant_sans_historique_avant_actualisation](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_priorite_nocturne_offline.py#L32) · paramètres self
- [test_carriere_manquante_avant_ferrures_meme_en_journee](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_priorite_nocturne_offline.py#L40) · paramètres self
- [test_selection_de_jour_conserve_priorite_aux_engagements_futurs](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_priorite_nocturne_offline.py#L51) · paramètres self
- [test_rattrapage_nuit_partant_avant_ancien_lien_deja_prouve](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_priorite_nocturne_offline.py#L60) · paramètres self
- [test_nuit_j1_avant_j0_et_anciens_dans_les_deux_collecteurs](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_priorite_nocturne_offline.py#L66) · paramètres self
- [test_nuit_priorite_j1_ne_contourne_pas_cooldown](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_priorite_nocturne_offline.py#L79) · paramètres self
- [test_nouvel_engagement_d_une_cible_ancienne_est_prioritaire_sans_changer_le_lot](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_priorite_nocturne_offline.py#L87) · paramètres self
- [test_pause_403_et_delais_de_reprise_restent_prioritaires](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_priorite_nocturne_offline.py#L94) · paramètres self
- [test_sync_echouee_se_reprend_sans_nouvelle_collecte_meme_la_nuit](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_priorite_nocturne_offline.py#L103) · paramètres self
- [seed_index](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_priorite_nocturne_offline.py#L109) · paramètres self, ambiguous=False
- [test_index_sauvegarde_resout_le_lien_du_partant_sans_requete_geny](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_priorite_nocturne_offline.py#L120) · paramètres self
- [test_index_course_ambigu_declenche_une_recherche_par_nom](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_priorite_nocturne_offline.py#L129) · paramètres self

### [tests/test_profils_partants_offline.py](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_profils_partants_offline.py)

Imports déclarés · dashboard.trot_analytics.profils, datetime, pathlib, pmu_geny.echeances_production, pmu_geny.moteur_sheets, pmu_geny.profils_partants, pmu_geny.sync_google_sheets, pmu_geny.top3_independants_v22, tempfile, test_v26_chaine_offline, unittest, unittest.mock
- [historique](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_profils_partants_offline.py#L24) · paramètres elite=False, rangs=('1', '2', '9', '8', '7', '5')
- [liaison](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_profils_partants_offline.py#L36) · paramètres document
- [test_regles_independantes_et_distance](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_profils_partants_offline.py#L41) · paramètres self
- [test_gains_crack_et_taux_de_disqualification](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_profils_partants_offline.py#L52) · paramètres self
- [test_potentiel_une_disqualification_admise_sur_dix_seulement](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_profils_partants_offline.py#L66) · paramètres self
- [test_rendez_vous_groupes_espaces_et_recents](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_profils_partants_offline.py#L77) · paramètres self
- [test_fuite_temporelle_et_discipline](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_profils_partants_offline.py#L100) · paramètres self
- [test_doublons_et_resultat_manquant](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_profils_partants_offline.py#L112) · paramètres self
- [test_etats_independants_et_historique_non_evaluable](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_profils_partants_offline.py#L123) · paramètres self
- [test_prevision_source_sheets_et_retrait](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_profils_partants_offline.py#L138) · paramètres self
- [test_formules_formats_idempotence_et_nouvelles_lignes](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_profils_partants_offline.py#L189) · paramètres self
- [__init__](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_profils_partants_offline.py#L191) · paramètres self
- [get](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_profils_partants_offline.py#L197) · paramètres self, url, **kwargs
- [post](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_profils_partants_offline.py#L205) · paramètres self, url, **kwargs

### [tests/test_publication_retraits_offline.py](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_publication_retraits_offline.py)

Imports déclarés · pathlib, pmu_geny.ml_v19, pmu_geny.sync_google_sheets, tempfile, unittest
- [test_source_transmet_les_vides_d_une_prevision_invalidee](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_publication_retraits_offline.py#L10) · paramètres self
- [test_rangs_selection_et_score_effaces_sur_retrait](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_publication_retraits_offline.py#L23) · paramètres self

### [tests/test_quotas_sheets_offline.py](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_quotas_sheets_offline.py)

Imports déclarés · copy, pathlib, pmu_geny.lectures_sheets, pmu_geny.moteur_sheets, pmu_geny.sync_google_sheets, tempfile, test_v26_chaine_offline, test_v29_moteur_unique_offline, unittest, unittest.mock
- [test_grille_23000_lignes_7_lectures_avec_cles_independantes_et_relecture](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_quotas_sheets_offline.py#L15) · paramètres self
- [get](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_quotas_sheets_offline.py#L17) · paramètres self, url, **kwargs
- [test_batch_incomplet_ou_mal_identifie_est_refuse](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_quotas_sheets_offline.py#L40) · paramètres self
- [test_429_attend_et_respecte_retry_after_sans_rejouer_ecriture](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_quotas_sheets_offline.py#L50) · paramètres self
- [test_429_retries_bornes_et_delai_long_sans_essai_anticipe](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_quotas_sheets_offline.py#L57) · paramètres self

### [tests/test_rapprochement_reunions_offline.py](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_rapprochement_reunions_offline.py)

Imports déclarés · datetime, hashlib, pathlib, pmu_geny, pmu_geny.kpi_registre, pmu_geny.sync_google_sheets, tempfile, unittest, unittest.mock
- [setUp](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_rapprochement_reunions_offline.py#L12) · paramètres self
- [write_programme](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_rapprochement_reunions_offline.py#L26) · paramètres self, day, courses
- [test_deux_reunions_meme_hippodrome_et_echeance_commune_aux_courses](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_rapprochement_reunions_offline.py#L29) · paramètres self
- [test_changement_heure_automne](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_rapprochement_reunions_offline.py#L40) · paramètres self
- [test_h30_provisoire_indisponible_et_reprise_ciblee](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_rapprochement_reunions_offline.py#L49) · paramètres self
- [test_scores_figes_alimentent_les_onglets_et_kpi](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_rapprochement_reunions_offline.py#L86) · paramètres self
- [test_un_bilan_issu_du_cache_filtre_est_rouvert](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_rapprochement_reunions_offline.py#L145) · paramètres self

### [tests/test_recensement_historiques_offline.py](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_recensement_historiques_offline.py)

Imports déclarés · datetime, pathlib, pmu_geny, tempfile, unittest, unittest.mock
- [test_examine_le_perimetre_et_reprend_apres_pause_sans_rejouer](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_recensement_historiques_offline.py#L12) · paramètres self
- [collecte](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_recensement_historiques_offline.py#L31) · paramètres horse, _
- [accepter](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_recensement_historiques_offline.py#L37) · paramètres _, horse, __
- [sync](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_recensement_historiques_offline.py#L40) · paramètres _

### [tests/test_recette_48h_offline.py](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_recette_48h_offline.py)

Imports déclarés · datetime, pathlib, pmu_geny, pmu_geny.auto_v18, pmu_geny.cycle_production, pmu_geny.moteur_sheets, pmu_geny.sync_google_sheets, tempfile, unittest, unittest.mock
- [test_collision_reprise_et_interdiction_de_certifier_sans_relecture](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_recette_48h_offline.py#L15) · paramètres self
- [test_jalon_avant_7h_et_global_restreint](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_recette_48h_offline.py#L91) · paramètres self
- [test_vrai_cycle_deux_jours_avec_panne_cron_et_arrivee_ex_aequo](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_recette_48h_offline.py#L103) · paramètres self
- [pmu](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_recette_48h_offline.py#L115) · paramètres url

### [tests/test_recette_finale_v21_offline.py](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_recette_finale_v21_offline.py)

Imports déclarés · contextlib, io, json, pathlib, pmu_geny, sys, tempfile, unittest, unittest.mock
- [test_registre_actif_accepte_les_ajouts_et_refuse_les_manques](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_recette_finale_v21_offline.py#L16) · paramètres self

### [tests/test_resolution_identites_courses_offline.py](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_resolution_identites_courses_offline.py)

Imports déclarés · datetime, pathlib, pmu_geny, pmu_geny.identites_chevaux, tempfile, unittest, unittest.mock
- [setUp](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_resolution_identites_courses_offline.py#L13) · paramètres self
- [course](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_resolution_identites_courses_offline.py#L22) · paramètres self, index, names, *, mapped=True
- [reply](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_resolution_identites_courses_offline.py#L39) · paramètres self, course
- [run_passage](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_resolution_identites_courses_offline.py#L48) · paramètres self, collect, stop=lambda: None
- [test_une_page_confirme_plusieurs_identites_et_priorise_la_course_la_plus_dense](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_resolution_identites_courses_offline.py#L52) · paramètres self
- [test_conflit_et_absence_ne_deviennent_pas_des_preuves](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_resolution_identites_courses_offline.py#L69) · paramètres self
- [collect](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_resolution_identites_courses_offline.py#L71) · paramètres course
- [test_403_partage_la_pause_et_la_cohorte_ne_change_pas](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_resolution_identites_courses_offline.py#L84) · paramètres self
- [test_page_publique_lue_une_fois_et_redirection_vers_autre_course_refusee](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_resolution_identites_courses_offline.py#L101) · paramètres self

### [tests/test_revalidation_diagnostics_offline.py](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_revalidation_diagnostics_offline.py)

Imports déclarés · copy, datetime, json, pathlib, pmu_geny, pmu_geny.collecte_geny_v4, pmu_geny.controle_historique, pmu_geny.revalider_diagnostics, tempfile, test_carriere_inedite_offline, unittest, unittest.mock, zipfile
- [setUp](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_revalidation_diagnostics_offline.py#L18) · paramètres self
- [archive](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_revalidation_diagnostics_offline.py#L33) · paramètres self, *, identity=True, document=None, geny=None, task=None, html=None
- [test_qualification_apres_derniere_course_ne_masque_pas_son_classement](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_revalidation_diagnostics_offline.py#L45) · paramètres self
- [test_rejeu_local_garde_date_ferrure_et_publie_sans_recollecte](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_revalidation_diagnostics_offline.py#L55) · paramètres self
- [test_identite_date_et_total_incertains_ne_sont_pas_promus](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_revalidation_diagnostics_offline.py#L73) · paramètres self
- [test_identifiants_artefacts_invalides_ne_declenchent_aucun_telechargement](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_revalidation_diagnostics_offline.py#L83) · paramètres self
- [test_conflit_d_identite_ne_peut_pas_etre_promu_depuis_une_archive](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_revalidation_diagnostics_offline.py#L90) · paramètres self
- [test_cible_sans_id_retrouvee_seulement_par_contexte_et_course_archivee](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_revalidation_diagnostics_offline.py#L97) · paramètres self
- [test_ancien_zero_avant_depart_ne_prouve_pas_la_carriere_vide_apres_depart](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_revalidation_diagnostics_offline.py#L112) · paramètres self

### [tests/test_schema_sheets_offline.py](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_schema_sheets_offline.py)

Imports déclarés · copy, pathlib, pmu_geny, pmu_geny.kpi_registre, pmu_geny.moteur_sheets, pmu_geny.sync_google_sheets, re, tempfile, test_v26_chaine_offline, unittest, unittest.mock
- [post](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_schema_sheets_offline.py#L15) · paramètres self, url, **kwargs
- [setUp](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_schema_sheets_offline.py#L29) · paramètres self
- [test_retrait_trois_onglets_sans_decalage_ni_recreation_au_deuxieme_passage](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_schema_sheets_offline.py#L35) · paramètres self
- [test_publication_exclut_les_champs_retires_et_garde_le_ml_et_les_cotes](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_schema_sheets_offline.py#L68) · paramètres self
- [test_date_capture_source_et_rang_arrivee_sans_manifeste](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_schema_sheets_offline.py#L80) · paramètres self
- [test_mises_a_jour_massives_regroupees_sans_ecraser_les_trous](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_schema_sheets_offline.py#L95) · paramètres self
- [test_kpi_ml_compte_les_selections_et_nettoie_les_formules_orphelines](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_schema_sheets_offline.py#L109) · paramètres self
- [test_moteur_lit_aussi_la_colonne_e_pour_effacer_les_references_orphelines](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_schema_sheets_offline.py#L117) · paramètres self

### [tests/test_sessions_et_historiques_partiels_offline.py](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_sessions_et_historiques_partiels_offline.py)

Imports déclarés · copy, datetime, json, pathlib, pmu_geny, pmu_geny.collecte_geny_v4, pmu_geny.historiques_partiels, pmu_geny.liaison_chevaux_v22, pmu_geny.ml_v19, pmu_geny.moteur_sheets, pmu_geny.sync_google_sheets, tempfile, test_v26_chaine_offline, test_v26_incremental_offline, unittest, unittest.mock
- [setUp](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_sessions_et_historiques_partiels_offline.py#L19) · paramètres self
- [test_un_seul_navigateur_et_la_page_ouverte_par_le_clic_est_reutilisee](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_sessions_et_historiques_partiels_offline.py#L29) · paramètres self
- [test_lien_connu_evite_la_resolution_de_la_course](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_sessions_et_historiques_partiels_offline.py#L45) · paramètres self
- [test_refus_a_la_resolution_arrete_avant_toute_extraction](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_sessions_et_historiques_partiels_offline.py#L55) · paramètres self
- [test_page_deja_chargee_refusee_sans_nouvelle_navigation](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_sessions_et_historiques_partiels_offline.py#L63) · paramètres self
- [test_resolution_sauvee_reprise_apres_arret_du_sous_processus](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_sessions_et_historiques_partiels_offline.py#L72) · paramètres self
- [setUp](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_sessions_et_historiques_partiels_offline.py#L84) · paramètres self
- [test_partiel_exploitable_sans_inventer_une_completion](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_sessions_et_historiques_partiels_offline.py#L95) · paramètres self
- [test_lignes_invalides_ou_futures_ecartees](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_sessions_et_historiques_partiels_offline.py#L108) · paramètres self
- [test_remplacement_du_partiel_archive_la_capture_precedente](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_sessions_et_historiques_partiels_offline.py#L116) · paramètres self
- [test_identite_refus_date_et_doublons_sont_bloquants](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_sessions_et_historiques_partiels_offline.py#L127) · paramètres self
- [test_complet_prioritaire_et_pas_de_doublon_dans_la_source_sheets](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_sessions_et_historiques_partiels_offline.py#L139) · paramètres self
- [test_publication_partielle_puis_complete_sans_reinsertion](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_sessions_et_historiques_partiels_offline.py#L150) · paramètres self
- [test_ml_distingue_partiel_et_complet_sans_modifier_les_instantanes](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_sessions_et_historiques_partiels_offline.py#L168) · paramètres self
- [test_cycle_compte_publie_et_reprend_le_partiel_sans_recollecte](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_sessions_et_historiques_partiels_offline.py#L182) · paramètres self
- [checkpoint](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_sessions_et_historiques_partiels_offline.py#L187) · paramètres cache
- [test_partiel_apres_une_course_officielle_ne_requiert_pas_un_fichier_complet](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_sessions_et_historiques_partiels_offline.py#L202) · paramètres self

### [tests/test_signaux_geny_offline.py](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_signaux_geny_offline.py)

Imports déclarés · datetime, pmu_geny.signaux_geny, unittest
- [setUp](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_signaux_geny_offline.py#L8) · paramètres self
- [performance](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_signaux_geny_offline.py#L22) · paramètres self, day, rank
- [test_signals_use_only_proven_earlier_rows](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_signaux_geny_offline.py#L28) · paramètres self
- [test_future_capture_and_ambiguous_dates_are_excluded](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_signaux_geny_offline.py#L35) · paramètres self
- [test_candidate_never_scores_an_unranked_runner](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_signaux_geny_offline.py#L42) · paramètres self

### [tests/test_streamlit_results_status_regression.py](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_streamlit_results_status_regression.py)

Imports déclarés · dashboard.trot_analytics.logic, dashboard.trot_analytics.performance, datetime
- [test_prestart_direct_result_with_stale_status_is_visible](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_streamlit_results_status_regression.py#L7) · paramètres aucun
- [test_poststart_prediction_is_never_accepted](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_streamlit_results_status_regression.py#L29) · paramètres aucun

### [tests/test_structure_geny_offline.py](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_structure_geny_offline.py)

Imports déclarés · pmu_geny.collecte_geny_v4, pmu_geny.migration_geny, pmu_geny.structure_geny, pmu_geny.sync_google_sheets, unittest
- [test_real_rows](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_structure_geny_offline.py#L14) · paramètres self
- [test_missing_and_ambiguous](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_structure_geny_offline.py#L30) · paramètres self
- [test_collection_keeps_raw](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_structure_geny_offline.py#L41) · paramètres self
- [test_mixed_legacy_and_idempotence](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_structure_geny_offline.py#L46) · paramètres self
- [test_sparse_write_skips_existing_cells](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_structure_geny_offline.py#L67) · paramètres self
- [test_regular_sync_preserves_real_legacy_url](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_structure_geny_offline.py#L71) · paramètres self

### [tests/test_v16_offline.py](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v16_offline.py)

Imports déclarés · json, pathlib, pmu_geny.collecte_geny_v4, pmu_geny.traitement_course, sys, tempfile, unittest.mock
- [fake](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v16_offline.py#L12) · paramètres url, ident, sortie
- [limit](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v16_offline.py#L28) · paramètres url, ident, sortie

### [tests/test_v17_offline.py](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v17_offline.py)

Imports déclarés · csv, json, pathlib, pmu_geny.export_v17, pmu_geny.participation_pmu, tempfile, unittest
Point d’entrée __main__ déclaré.
- [setUp](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v17_offline.py#L7) · paramètres self
- [test_empty_control_means_unknown](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v17_offline.py#L17) · paramètres self
- [test_pmu_confirmation_and_export](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v17_offline.py#L25) · paramètres self
- [test_partial_confirmation](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v17_offline.py#L33) · paramètres self
- [test_unverified_source_refused](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v17_offline.py#L38) · paramètres self

### [tests/test_v18_offline.py](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v18_offline.py)

Imports déclarés · datetime, json, pathlib, pmu_geny.auto_v18, pmu_geny.pronostics_v18, tempfile, unittest, zoneinfo
Point d’entrée __main__ déclaré.
- [setUp](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v18_offline.py#L9) · paramètres self
- [test_programme_france](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v18_offline.py#L14) · paramètres self
- [test_np_zero_requires_all_flags](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v18_offline.py#L18) · paramètres self
- [test_np_and_frozen_top3](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v18_offline.py#L23) · paramètres self

### [tests/test_v19_offline.py](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v19_offline.py)

Imports déclarés · csv, datetime, json, pathlib, pmu_geny.auto_v18, pmu_geny.cotes_v19, pmu_geny.ml_v19, pmu_geny.pronostics_v18, tempfile, unittest, zoneinfo
Point d’entrée __main__ déclaré.
- [setUp](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v19_offline.py#L10) · paramètres self
- [test_no_odds_in_features](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v19_offline.py#L18) · paramètres self
- [test_ml_requires_labeled_historical_courses](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v19_offline.py#L22) · paramètres self
- [test_cotes_before_start_only](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v19_offline.py#L27) · paramètres self
- [test_dernier_rapport_direct](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v19_offline.py#L34) · paramètres self
- [test_retrait_updates_baseline_and_csv](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v19_offline.py#L45) · paramètres self

### [tests/test_v20_1_audit_offline.py](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v20_1_audit_offline.py)

Imports déclarés · json, pathlib, pmu_geny.audit_predictif_v20_1, pmu_geny.ml_v19, tempfile, unittest
Point d’entrée __main__ déclaré.
- [test_audit_et_exclusion_cotes](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v20_1_audit_offline.py#L7) · paramètres self
- [write](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v20_1_audit_offline.py#L11) · paramètres rel, data
- [test_pas_audit_sans_arrivee](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v20_1_audit_offline.py#L27) · paramètres self

### [tests/test_v20_2_scheduler_offline.py](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v20_2_scheduler_offline.py)

Imports déclarés · datetime, pmu_geny.planification_v20_2, unittest, zoneinfo
Point d’entrée __main__ déclaré.
- [race](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v20_2_scheduler_offline.py#L9) · paramètres code, departure
- [test_day_before_as_soon_as_programme_available](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v20_2_scheduler_offline.py#L13) · paramètres self
- [test_priority_and_no_future_on_light](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v20_2_scheduler_offline.py#L18) · paramètres self
- [test_finished_only_in_36h_and_no_future_on_light](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v20_2_scheduler_offline.py#L22) · paramètres self
- [test_archived_excluded](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v20_2_scheduler_offline.py#L28) · paramètres self
- [test_cap](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v20_2_scheduler_offline.py#L31) · paramètres self

### [tests/test_v20_3_pmu_diagnostic_offline.py](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v20_3_pmu_diagnostic_offline.py)

Imports déclarés · datetime, pmu_geny.auto_v18, unittest
Point d’entrée __main__ déclaré.
- [setUp](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v20_3_pmu_diagnostic_offline.py#L6) · paramètres self
- [test_country_in_reunion](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v20_3_pmu_diagnostic_offline.py#L10) · paramètres self
- [test_country_in_hippodrome](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v20_3_pmu_diagnostic_offline.py#L15) · paramètres self
- [test_unknown_not_assumed_france](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v20_3_pmu_diagnostic_offline.py#L19) · paramètres self
- [test_invalid_partants_reported](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v20_3_pmu_diagnostic_offline.py#L25) · paramètres self

### [tests/test_v20_4_selection_metier_offline.py](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v20_4_selection_metier_offline.py)

Imports déclarés · datetime, pmu_geny.auto_v18, pmu_geny.planification_v20_2, pmu_geny.selection_metier_v20_4, unittest, zoneinfo
Point d’entrée __main__ déclaré.
- [setUp](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v20_4_selection_metier_offline.py#L9) · paramètres self
- [c](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v20_4_selection_metier_offline.py#L12) · paramètres self, n, disc='TROT_ATTELE', nb=14, alloc=21000
- [run_prog](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v20_4_selection_metier_offline.py#L15) · paramètres self, reunions
- [r](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v20_4_selection_metier_offline.py#L17) · paramètres self, rno, hip, courses, **kwargs
- [test_trot_exclusive_et_priorites](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v20_4_selection_metier_offline.py#L19) · paramètres self
- [test_absence_discipline_pas_deduction_depuis_nom](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v20_4_selection_metier_offline.py#L30) · paramètres self
- [test_specialite_unique_reunion](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v20_4_selection_metier_offline.py#L35) · paramètres self
- [test_mix_reunion_non_suffisant](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v20_4_selection_metier_offline.py#L39) · paramètres self
- [test_depart_hors_plage](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v20_4_selection_metier_offline.py#L43) · paramètres self
- [test_limites_07_21_paris](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v20_4_selection_metier_offline.py#L49) · paramètres self
- [test_groupe_et_allocation](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v20_4_selection_metier_offline.py#L57) · paramètres self
- [test_p2_seuil](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v20_4_selection_metier_offline.py#L63) · paramètres self
- [test_horaire_prioritaire_puis_p1](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v20_4_selection_metier_offline.py#L66) · paramètres self
- [horse](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v20_4_selection_metier_offline.py#L68) · paramètres code, hours, tier

### [tests/test_v20_5_hippodromes_j1_offline.py](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v20_5_hippodromes_j1_offline.py)

Imports déclarés · datetime, pmu_geny.auto_v18, pmu_geny.planification_v20_2, pmu_geny.selection_metier_v20_4, unittest, zoneinfo
Point d’entrée __main__ déclaré.
- [course](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v20_5_hippodromes_j1_offline.py#L11) · paramètres self, n, heure=15, allocation=33000
- [test_vincennes_pmu_p1_sans_allocation_elevee](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v20_5_hippodromes_j1_offline.py#L14) · paramètres self
- [test_reims_p2_normalise](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v20_5_hippodromes_j1_offline.py#L20) · paramètres self
- [test_lyon_sites_distincts](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v20_5_hippodromes_j1_offline.py#L24) · paramètres self
- [test_non_trot_exclu_memes_si_vincennes](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v20_5_hippodromes_j1_offline.py#L27) · paramètres self
- [test_diagnostic_course_pmu_reclassee](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v20_5_hippodromes_j1_offline.py#L30) · paramètres self
- [test_course_terminee_non_preparee](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v20_5_hippodromes_j1_offline.py#L35) · paramètres self
- [test_preparation_demain_apres_18](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v20_5_hippodromes_j1_offline.py#L40) · paramètres self

### [tests/test_v20_6_rapprochement_offline.py](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v20_6_rapprochement_offline.py)

Imports déclarés · datetime, pmu_geny.planification_v20_2, pmu_geny.rapprochement_v20_6, unittest, zoneinfo
Point d’entrée __main__ déclaré.
- [test_vincennes_exact](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v20_6_rapprochement_offline.py#L8) · paramètres self
- [test_other_hippodrome_never_matched](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v20_6_rapprochement_offline.py#L16) · paramètres self
- [test_short_name_sponsor](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v20_6_rapprochement_offline.py#L20) · paramètres self
- [test_ambiguous_same_race](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v20_6_rapprochement_offline.py#L24) · paramètres self
- [test_no_name_match](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v20_6_rapprochement_offline.py#L28) · paramètres self
- [test_future_selection_on_light_when_explicitly_enabled](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v20_6_rapprochement_offline.py#L32) · paramètres self
- [test_dedup_links](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v20_6_rapprochement_offline.py#L37) · paramètres self

### [tests/test_v20_7_rc_offline.py](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v20_7_rc_offline.py)

Imports déclarés · pmu_geny.rapprochement_v20_6, unittest
Point d’entrée __main__ déclaré.
- [test_direct](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v20_7_rc_offline.py#L8) · paramètres self
- [test_wrong_hippodrome](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v20_7_rc_offline.py#L12) · paramètres self
- [test_wrong_date](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v20_7_rc_offline.py#L15) · paramètres self
- [test_duplicate_codes](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v20_7_rc_offline.py#L18) · paramètres self
- [test_conflicting_name](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v20_7_rc_offline.py#L21) · paramètres self
- [test_fallback](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v20_7_rc_offline.py#L24) · paramètres self
- [test_conflicting_codes_matched_only_when_name_strict](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v20_7_rc_offline.py#L27) · paramètres self
- [test_index_keeps_rc](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v20_7_rc_offline.py#L30) · paramètres self

### [tests/test_v20_8_bridge_offline.py](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v20_8_bridge_offline.py)

Imports déclarés · pmu_geny.sync_google_sheets, unittest
Point d’entrée __main__ déclaré.
- [test_cols](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v20_8_bridge_offline.py#L4) · paramètres self
- [test_hippodrome_normalise](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v20_8_bridge_offline.py#L5) · paramètres self
- [test_course_key](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v20_8_bridge_offline.py#L6) · paramètres self
- [test_idempotent_update](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v20_8_bridge_offline.py#L7) · paramètres self
- [test_append](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v20_8_bridge_offline.py#L12) · paramètres self
- [test_missing_key_fails](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v20_8_bridge_offline.py#L15) · paramètres self

### [tests/test_v20_9_rapprochement_reel_offline.py](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v20_9_rapprochement_reel_offline.py)

Imports déclarés · pmu_geny.rapprochement_v20_6, unittest
Point d’entrée __main__ déclaré.
- [candidate](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v20_9_rapprochement_reel_offline.py#L8) · paramètres self, course_id, lieu, titre, r=None, c=None
- [test_la_capelle_reunion_renumerotee](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v20_9_rapprochement_reel_offline.py#L13) · paramètres self
- [test_la_capelle_exact_code](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v20_9_rapprochement_reel_offline.py#L26) · paramètres self
- [test_lyon_nom_et_hippodrome_sans_code](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v20_9_rapprochement_reel_offline.py#L33) · paramètres self
- [test_nom_proche_different_refuse_avec_code_contradictoire](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v20_9_rapprochement_reel_offline.py#L39) · paramètres self
- [test_deux_noms_identiques_refuses](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v20_9_rapprochement_reel_offline.py#L45) · paramètres self
- [test_mauvaise_date_et_piste_refusees](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v20_9_rapprochement_reel_offline.py#L52) · paramètres self

### [tests/test_v20_meteo_offline.py](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v20_meteo_offline.py)

Imports déclarés · datetime, json, pathlib, pmu_geny.contexte_meteo_v20, pmu_geny.ml_v19, pmu_geny.sync_google_sheets, tempfile, unittest
Point d’entrée __main__ déclaré.
- [setUp](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v20_meteo_offline.py#L8) · paramètres self
- [test_weather_ingested_before_depart](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v20_meteo_offline.py#L16) · paramètres self
- [test_no_postdeparture_weather](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v20_meteo_offline.py#L24) · paramètres self
- [test_missing_values_not_faked](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v20_meteo_offline.py#L27) · paramètres self
- [test_no_network_call_when_recent](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v20_meteo_offline.py#L31) · paramètres self
- [fail](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v20_meteo_offline.py#L33) · paramètres *args
- [test_verified_racetrack_locations_without_geocode_http](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v20_meteo_offline.py#L35) · paramètres self
- [test_sheet_consolidates_weather_without_fake_values](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v20_meteo_offline.py#L42) · paramètres self

### [tests/test_v21_coherence_offline.py](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v21_coherence_offline.py)

Imports déclarés · csv, datetime, json, pathlib, pmu_geny.auto_v18, pmu_geny.collecte_geny_v4, pmu_geny.controle_historique, pmu_geny.sync_google_sheets, tempfile, unittest, zoneinfo
Point d’entrée __main__ déclaré.
- [test_perimetre_france_trot_07_21](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v21_coherence_offline.py#L17) · paramètres self
- [test_deux_performances_distinctes_meme_date](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v21_coherence_offline.py#L26) · paramètres self
- [test_codes_de_classement_source](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v21_coherence_offline.py#L35) · paramètres self
- [test_export_deux_courses_meme_date_vers_sheets](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v21_coherence_offline.py#L39) · paramètres self

### [tests/test_v21_paliers_offline.py](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v21_paliers_offline.py)

Imports déclarés · csv, datetime, json, pathlib, pmu_geny.ml_v19, pmu_geny.partants_actuels_v21, pmu_geny.planification_v20_2, pmu_geny.pronostics_v18, pmu_geny.resultats_v18, pmu_geny.sync_google_sheets, pmu_geny.top3_independants_v22, tempfile, unittest, zoneinfo
Point d’entrée __main__ déclaré.
- [test_champs_pmu_explicitement_extraits](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v21_paliers_offline.py#L13) · paramètres self
- [test_deux_paliers_sans_inventer_ml](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v21_paliers_offline.py#L28) · paramètres self
- [write](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v21_paliers_offline.py#L31) · paramètres path, obj
- [test_top3_np_inconnu_rattrapage_avant_depart](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v21_paliers_offline.py#L78) · paramètres self
- [test_reset_preserves_histories_and_blocks_old_courses](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v21_paliers_offline.py#L105) · paramètres self
- [test_resultat_pmu_sans_manifest_geny](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v21_paliers_offline.py#L120) · paramètres self
- [test_v22_trois_niveaux_independants_du_manifeste](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v21_paliers_offline.py#L156) · paramètres self
- [test_v22_comparaison_trois_top3_avec_arrivee](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v21_paliers_offline.py#L202) · paramètres self
- [write](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v21_paliers_offline.py#L208) · paramètres rel, data
- [test_preparation_j1_avant_18h](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v21_paliers_offline.py#L229) · paramètres self
- [test_v22_capture_pmu_sans_manifest_avec_historique_cache](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v21_paliers_offline.py#L244) · paramètres self
- [write](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v21_paliers_offline.py#L249) · paramètres rel, doc
- [test_v22_historiques_canoniques_visibles_sans_export_geny](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v21_paliers_offline.py#L280) · paramètres self
- [write](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v21_paliers_offline.py#L283) · paramètres rel, doc
- [test_v22_entetes_lisibles_et_moteur_inchange](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v21_paliers_offline.py#L299) · paramètres self
- [test_registre_11_novembre_reel](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v21_paliers_offline.py#L313) · paramètres self

### [tests/test_v22_avis_identite_offline.py](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v22_avis_identite_offline.py)

Imports déclarés · datetime, json, pathlib, pmu_geny.avis_experts_v22, pmu_geny.liaison_chevaux_v22, pmu_geny.partants_actuels_v21, pmu_geny.sync_google_sheets, tempfile, unittest
Point d’entrée __main__ déclaré.
- [setUp](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v22_avis_identite_offline.py#L22) · paramètres self
- [write](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v22_avis_identite_offline.py#L25) · paramètres self, path, data
- [test_date_source](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v22_avis_identite_offline.py#L28) · paramètres self
- [test_zone_expert_exact_num_name_before_depart](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v22_avis_identite_offline.py#L31) · paramètres self
- [test_ambiguous_horse_name_and_race_never_attributed](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v22_avis_identite_offline.py#L44) · paramètres self
- [test_stable_geny_id_first_over_name](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v22_avis_identite_offline.py#L47) · paramètres self
- [test_partant_age_sexe_gains_ferrure](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v22_avis_identite_offline.py#L68) · paramètres self
- [test_public_pmu_centimes_and_shoeing_enums](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v22_avis_identite_offline.py#L77) · paramètres self
- [test_historic_ferrure_explicit_only](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v22_avis_identite_offline.py#L96) · paramètres self
- [test_real_archived_zone_profile](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v22_avis_identite_offline.py#L100) · paramètres self
- [test_report_fields_are_compact_and_essential](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v22_avis_identite_offline.py#L114) · paramètres self

### [tests/test_v23_sources_offline.py](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v23_sources_offline.py)

Imports déclarés · datetime, json, pathlib, pmu_geny.ml_v19, pmu_geny.partants_actuels_v21, pmu_geny.sources_experts_v23, pmu_geny.sync_google_sheets, tempfile, unittest, unittest.mock
Point d’entrée __main__ déclaré.
- [eqhtml](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v23_sources_offline.py#L17) · paramètres d=EQ
- [setUp](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v23_sources_offline.py#L21) · paramètres self
- [fetch](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v23_sources_offline.py#L23) · paramètres self, url · retours littéraux <a href="/fr/course-du-jour/2026-11-12/R3C1-vincennes-prix-test">Test</a>, <a href="/fr/reunion-du-jour/2026-11-12/R3-vincennes">Vincennes</a>
- [test_observed_schemas_and_gain_not_chrono](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v23_sources_offline.py#L30) · paramètres self
- [test_wrong_race_date_name_and_horse_rejected](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v23_sources_offline.py#L36) · paramètres self
- [test_collecte_pmu_seule_cache_et_aucun_complement_tiers](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v23_sources_offline.py#L42) · paramètres self
- [fetch](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v23_sources_offline.py#L45) · paramètres url
- [test_secondary_title_and_changed_horse](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v23_sources_offline.py#L58) · paramètres self
- [test_same_race_links_with_bet_queries_are_one_candidate](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v23_sources_offline.py#L62) · paramètres self
- [test_after_depart_no_fetch_or_write](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v23_sources_offline.py#L64) · paramètres self
- [test_unavailable_never_neutral_and_legacy_not_relabelled](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v23_sources_offline.py#L68) · paramètres self
- [fail](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v23_sources_offline.py#L69) · paramètres url
- [test_empty_expert_value_clears_stale_cell](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v23_sources_offline.py#L76) · paramètres self
- [test_colonne_equidia_supprimee_non_recreee_et_voisine_preservee](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v23_sources_offline.py#L81) · paramètres self
- [test_caracteristiques_pmu_sont_conservees_sans_lecture_tierce](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v23_sources_offline.py#L89) · paramètres self
- [test_anciens_avis_tiers_ne_sont_plus_republies](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v23_sources_offline.py#L96) · paramètres self
- [test_anciens_complements_tiers_retires_sans_effacer_pmu](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v23_sources_offline.py#L109) · paramètres self
- [test_reseau_equidia_et_zeturf_refuse_avant_requete](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v23_sources_offline.py#L122) · paramètres self
- [test_capture_ml_ne_complete_plus_les_criteres_depuis_zone_turf](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v23_sources_offline.py#L129) · paramètres self
- [test_vider_un_critere_courant_ne_vide_pas_une_ferrure_historique](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v23_sources_offline.py#L144) · paramètres self

### [tests/test_v24_fiabilite_offline.py](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v24_fiabilite_offline.py)

Imports déclarés · datetime, json, pathlib, pmu_geny.kpi_registre, pmu_geny.pronostics_v18, pmu_geny.qualite_registre_v21, pmu_geny.sync_google_sheets, pmu_geny.top3_independants_v22, tempfile, unittest
Point d’entrée __main__ déclaré.
- [write](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v24_fiabilite_offline.py#L15) · paramètres path, doc
- [test_compact_and_spaced_have_identical_tokens_and_score](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v24_fiabilite_offline.py#L20) · paramètres self
- [test_years_and_two_digit_positions](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v24_fiabilite_offline.py#L25) · paramètres self
- [test_disqualifications_do_not_hide_the_next_performance](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v24_fiabilite_offline.py#L30) · paramètres self
- [test_archive_and_invalid_formats](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v24_fiabilite_offline.py#L35) · paramètres self
- [setUp](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v24_fiabilite_offline.py#L41) · paramètres self
- [document](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v24_fiabilite_offline.py#L50) · paramètres self, mode
- [np](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v24_fiabilite_offline.py#L52) · paramètres self, minutes=0, withdrawn=(1,)
- [test_withdrawal_refreshes_both_direct_and_market](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v24_fiabilite_offline.py#L55) · paramètres self
- [test_withdrawal_persists_when_next_flag_is_unknown](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v24_fiabilite_offline.py#L66) · paramètres self
- [test_explicit_reinstatement_is_recorded](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v24_fiabilite_offline.py#L73) · paramètres self
- [test_insufficient_remaining_horses_invalidates_latest_selection](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v24_fiabilite_offline.py#L80) · paramètres self
- [test_no_retroactive_update](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v24_fiabilite_offline.py#L88) · paramètres self
- [test_stale_np_is_excluded_from_initial_baseline](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v24_fiabilite_offline.py#L95) · paramètres self
- [test_future_np_is_not_used](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v24_fiabilite_offline.py#L101) · paramètres self
- [test_stale_np_updates_baseline_without_changing_original](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v24_fiabilite_offline.py#L106) · paramètres self
- [test_zero_score_is_numeric_even_when_previous_score_is_text](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v24_fiabilite_offline.py#L116) · paramètres self
- [test_withdrawn_selection_and_rank_are_cleared_in_sheet](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v24_fiabilite_offline.py#L123) · paramètres self
- [test_numeric_append_and_idempotence](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v24_fiabilite_offline.py#L128) · paramètres self
- [setUp](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v24_fiabilite_offline.py#L135) · paramètres self
- [test_zero_hits_are_evaluated_and_histories_require_positive_number](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v24_fiabilite_offline.py#L141) · paramètres self
- [test_post_departure_prediction_is_not_evaluated](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v24_fiabilite_offline.py#L151) · paramètres self
- [test_kpi_updates_follow_labels_instead_of_fixed_positions](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v24_fiabilite_offline.py#L157) · paramètres self
- [test_real_reference_reconciles_all_13_races_and_historical_baseline](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v24_fiabilite_offline.py#L166) · paramètres self

### [tests/test_v26_chaine_offline.py](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v26_chaine_offline.py)

Imports déclarés · dashboard.trot_analytics.dates, dashboard.trot_analytics.logic, datetime, json, pathlib, pmu_geny, pmu_geny.auto_v18, pmu_geny.controle_sync_sheets, pmu_geny.moteur_sheets, pmu_geny.planification_v20_2, pmu_geny.sync_google_sheets, re, scripts.synchroniser_un_historique, subprocess, tempfile, unittest, unittest.mock, urllib.parse, zoneinfo
Point d’entrée __main__ déclaré.
- [__init__](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v26_chaine_offline.py#L17) · paramètres self, data
- [raise_for_status](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v26_chaine_offline.py#L19) · paramètres self
- [json](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v26_chaine_offline.py#L21) · paramètres self
- [__init__](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v26_chaine_offline.py#L26) · paramètres self
- [get](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v26_chaine_offline.py#L34) · paramètres self, url, **kwargs
- [column](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v26_chaine_offline.py#L47) · paramètres label
- [post](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v26_chaine_offline.py#L54) · paramètres self, url, **kwargs
- [test_migration_dates_sheets_preserve_colonnes_et_version](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v26_chaine_offline.py#L81) · paramètres self
- [test_instants_operationnels_sheets_et_streamlit](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v26_chaine_offline.py#L110) · paramètres self
- [test_plan_corrompu_bloque_avant_tout_post_sheets](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v26_chaine_offline.py#L146) · paramètres self
- [test_cycle_pmu_alimente_file_sans_collecte_geny_et_respecte_jour_j](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v26_chaine_offline.py#L163) · paramètres self
- [test_sheets_idempotent_sans_toucher_top3_ni_formule_kpi](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v26_chaine_offline.py#L196) · paramètres self
- [test_checkpoint_git_reel_rechargeable_et_fichiers_figes_intacts](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v26_chaine_offline.py#L222) · paramètres self
- [git](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v26_chaine_offline.py#L226) · paramètres *args, cwd=None
- [test_fenetres_decision_jour_j_et_dst](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v26_chaine_offline.py#L256) · paramètres self

### [tests/test_v26_incremental_offline.py](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v26_incremental_offline.py)

Imports déclarés · copy, datetime, json, pathlib, pmu_geny, pmu_geny.collecte_geny_v4, pmu_geny.controle_historique, tempfile, unittest, unittest.mock
Point d’entrée __main__ déclaré.
- [doc](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v26_incremental_offline.py#L16) · paramètres stamp, rows=None
- [test_resultat_tb_explicite_ne_bloque_pas_une_carriere_complete](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v26_incremental_offline.py#L27) · paramètres self
- [setUp](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v26_incremental_offline.py#L34) · paramètres self
- [seed](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v26_incremental_offline.py#L52) · paramètres self, stamp=None
- [collect](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v26_incremental_offline.py#L60) · paramètres self, horse, out
- [test_reutilise_les_liens_de_course_dans_le_meme_passage_sans_pause](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v26_incremental_offline.py#L68) · paramètres self
- [collect](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v26_incremental_offline.py#L75) · paramètres horse, out
- [test_capture_validee_annule_un_ancien_delai_d_echec](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v26_incremental_offline.py#L99) · paramètres self
- [test_echec_garde_les_motifs_et_les_compteurs_distincts](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v26_incremental_offline.py#L107) · paramètres self
- [test_production_cede_apres_sauvegarde_et_publication_du_cheval](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v26_incremental_offline.py#L119) · paramètres self
- [test_migration_utilise_date_source_pas_date_migration](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v26_incremental_offline.py#L130) · paramètres self
- [test_complete_recent_aucune_requete](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v26_incremental_offline.py#L136) · paramètres self
- [interdit](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v26_incremental_offline.py#L138) · paramètres *args
- [test_date_absente_non_fabriquee](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v26_incremental_offline.py#L143) · paramètres self
- [test_nouvelle_course_declenche_actualisation_avant_ttl](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v26_incremental_offline.py#L151) · paramètres self
- [test_publication_geny_retardee_reste_a_completer](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v26_incremental_offline.py#L157) · paramètres self
- [test_checkpoint_avant_sheets_et_sans_recollecte_au_second_passage](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v26_incremental_offline.py#L164) · paramètres self
- [checkpoint](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v26_incremental_offline.py#L167) · paramètres cache
- [sync](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v26_incremental_offline.py#L171) · paramètres h
- [test_erreur_sheets_reprise_sans_geny](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v26_incremental_offline.py#L184) · paramètres self
- [fail](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v26_incremental_offline.py#L186) · paramètres h
- [interdit](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v26_incremental_offline.py#L192) · paramètres *args
- [test_refus_global_403_et_429](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v26_incremental_offline.py#L198) · paramètres self
- [refuse](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v26_incremental_offline.py#L204) · paramètres h, out
- [test_historique_plus_pauvre_ne_remplace_pas_existant](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v26_incremental_offline.py#L212) · paramètres self
- [test_partiel_ne_remplace_pas_complet](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v26_incremental_offline.py#L221) · paramètres self
- [test_identifiant_different_refuse](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v26_incremental_offline.py#L229) · paramètres self
- [test_ancien_snapshot_archive_et_pronostics_intacts](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v26_incremental_offline.py#L234) · paramètres self
- [test_deux_courses_meme_cheval_un_seul_travail](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v26_incremental_offline.py#L246) · paramètres self
- [test_np_non_mis_en_file](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v26_incremental_offline.py#L253) · paramètres self
- [test_etat_corrompu_arrete_sans_effacer](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v26_incremental_offline.py#L258) · paramètres self
- [test_checkpoint_echoue_arrete_avant_requete](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v26_incremental_offline.py#L266) · paramètres self
- [checkpoint](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v26_incremental_offline.py#L267) · paramètres cache
- [collect](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v26_incremental_offline.py#L269) · paramètres *args
- [test_manifest_materialise_seulement_si_identites_completes](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v26_incremental_offline.py#L274) · paramètres self
- [test_nouvelle_identite_reprise_sous_id_stable](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v26_incremental_offline.py#L282) · paramètres self
- [test_dpg_conserve_sans_place_inventee](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v26_incremental_offline.py#L287) · paramètres self
- [test_suffixe_video_reel_ne_masque_pas_dai](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v26_incremental_offline.py#L291) · paramètres self

### [tests/test_v27_sheets_pagination_offline.py](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v27_sheets_pagination_offline.py)

Imports déclarés · pmu_geny.sync_google_sheets, unittest, unittest.mock, urllib.parse
Point d’entrée __main__ déclaré.
- [__init__](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v27_sheets_pagination_offline.py#L9) · paramètres self, code, values
- [json](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v27_sheets_pagination_offline.py#L10) · paramètres self
- [test_cle_apres_5000_ne_se_reinsere_pas](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v27_sheets_pagination_offline.py#L14) · paramètres self
- [get](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v27_sheets_pagination_offline.py#L16) · paramètres self, url, **kwargs
- [test_groupe_les_pages_et_conserve_les_trous_entre_appels](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v27_sheets_pagination_offline.py#L33) · paramètres self
- [__init__](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v27_sheets_pagination_offline.py#L35) · paramètres self
- [get](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v27_sheets_pagination_offline.py#L38) · paramètres self, url, **kwargs
- [test_page_incomplete_arrete_lecture](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v27_sheets_pagination_offline.py#L56) · paramètres self
- [get](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v27_sheets_pagination_offline.py#L58) · paramètres self, url, **kwargs
- [test_429_retente_sans_prendre_une_page_vide_pour_un_succes](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v27_sheets_pagination_offline.py#L62) · paramètres self
- [get](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v27_sheets_pagination_offline.py#L65) · paramètres self, url, **kwargs
- [test_dimensions_absentes_refusees](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v27_sheets_pagination_offline.py#L74) · paramètres self
- [test_variantes_meme_cle_conservees_sans_ecrasement_ni_reinsertion](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v27_sheets_pagination_offline.py#L77) · paramètres self

### [tests/test_v28_controles_sync_offline.py](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v28_controles_sync_offline.py)

Imports déclarés · collections, json, os, pathlib, pmu_geny.controle_sync_sheets, pmu_geny.sync_google_sheets, tempfile, unittest, unittest.mock
Point d’entrée __main__ déclaré.
- [setUp](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v28_controles_sync_offline.py#L14) · paramètres self
- [control](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v28_controles_sync_offline.py#L21) · paramètres self, existing, incoming, appends=None, observed=None
- [test_rejouer_la_meme_source_ne_cree_aucune_ligne](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v28_controles_sync_offline.py#L26) · paramètres self
- [test_meme_cle_dans_deux_entrees_source_refusee](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v28_controles_sync_offline.py#L34) · paramètres self
- [test_proposition_de_reinsertion_refusee_avant_post](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v28_controles_sync_offline.py#L38) · paramètres self
- [test_lecture_tronquee_detectee_par_le_controle_independant](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v28_controles_sync_offline.py#L43) · paramètres self
- [test_doublons_de_valeurs_existants_bloquent_sans_supprimer](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v28_controles_sync_offline.py#L48) · paramètres self
- [test_variantes_existantes_de_meme_cle_sont_bloquees](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v28_controles_sync_offline.py#L54) · paramètres self
- [test_croissance_anormale_refusee](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v28_controles_sync_offline.py#L60) · paramètres self
- [test_seuil_relatif_sur_un_historique_plus_grand](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v28_controles_sync_offline.py#L65) · paramètres self
- [test_import_initial_explicite_et_trace](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v28_controles_sync_offline.py#L71) · paramètres self
- [test_ligne_inattendue_apres_post_detectee](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v28_controles_sync_offline.py#L78) · paramètres self
- [test_ligne_perdue_apres_post_detectee](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v28_controles_sync_offline.py#L84) · paramètres self
- [test_echec_produit_un_journal_et_un_resume_explicitement_bloques](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v28_controles_sync_offline.py#L90) · paramètres self
- [test_source_complete_inattendue_vide_bloquee](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v28_controles_sync_offline.py#L96) · paramètres self

### [tests/test_v29_moteur_unique_offline.py](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v29_moteur_unique_offline.py)

Imports déclarés · copy, datetime, json, os, pathlib, pmu_geny, pmu_geny.controle_sync_sheets, pmu_geny.moteur_sheets, scripts.synchroniser_un_historique, tempfile, test_v26_chaine_offline, test_v26_incremental_offline, unittest, unittest.mock, yaml
Point d’entrée __main__ déclaré.
- [__init__](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v29_moteur_unique_offline.py#L15) · paramètres self
- [get](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v29_moteur_unique_offline.py#L17) · paramètres self, url, **kwargs
- [setUp](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v29_moteur_unique_offline.py#L22) · paramètres self
- [test_les_deux_declencheurs_donnent_le_meme_historique](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v29_moteur_unique_offline.py#L33) · paramètres self
- [test_suppression_equidia_puis_actualisation_de_la_voisine_sans_decalage](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v29_moteur_unique_offline.py#L44) · paramètres self
- [post](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v29_moteur_unique_offline.py#L46) · paramètres self, url, **kwargs
- [test_verrou_local_refuse_un_second_ecrivain_avant_toute_requete](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v29_moteur_unique_offline.py#L71) · paramètres self
- [test_echec_maj_ne_poursuit_pas_avec_les_ajouts](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v29_moteur_unique_offline.py#L80) · paramètres self
- [post](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v29_moteur_unique_offline.py#L82) · paramètres self, url, **kwargs
- [test_append_commis_mais_reponse_perdue_reprise_sans_doublon](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v29_moteur_unique_offline.py#L94) · paramètres self
- [post](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v29_moteur_unique_offline.py#L97) · paramètres self, url, **kwargs
- [test_anomalie_historique_bloque_avant_modification_des_autres_onglets](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v29_moteur_unique_offline.py#L109) · paramètres self
- [test_consolidation_kpi_et_connexion_une_fois_par_passage](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v29_moteur_unique_offline.py#L119) · paramètres self
- [simulate](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v29_moteur_unique_offline.py#L122) · paramètres shared
- [source](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v29_moteur_unique_offline.py#L126) · paramètres *args
- [test_workflows_partagent_le_verrou_et_ne_s_annulent_pas](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v29_moteur_unique_offline.py#L159) · paramètres self
- [test_reprise_kpi_seule_sans_recollecter_ni_republier_les_chevaux](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v29_moteur_unique_offline.py#L170) · paramètres self
- [collect](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v29_moteur_unique_offline.py#L182) · paramètres horse, out

### [tests/test_v30_rattrapage_offline.py](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v30_rattrapage_offline.py)

Imports déclarés · copy, datetime, json, os, pathlib, pmu_geny, pmu_geny.echeances_production, pmu_geny.historique_individuel, pmu_geny.moteur_sheets, pmu_geny.preparation_prochaines, subprocess, tempfile, test_v26_chaine_offline, test_v26_incremental_offline, unittest, unittest.mock, yaml, zoneinfo
Point d’entrée __main__ déclaré.
- [setUp](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v30_rattrapage_offline.py#L20) · paramètres self
- [seed](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v30_rattrapage_offline.py#L28) · paramètres self, *, complete=False, covered=False
- [collect](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v30_rattrapage_offline.py#L42) · paramètres self, horse, out
- [test_passe_ancien_np_journal_et_sheet_sans_fenetre_glissante](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v30_rattrapage_offline.py#L47) · paramètres self
- [test_inventaire_fige_ne_perd_pas_les_cibles_ni_ne_grossit_a_chaque_passage](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v30_rattrapage_offline.py#L57) · paramètres self
- [test_extension_explicite_archive_l_ancien_lot_et_conserve_les_preuves](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v30_rattrapage_offline.py#L66) · paramètres self
- [test_lot_96_suit_une_reconciliation_prouvee_sans_changer_de_denominateur](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v30_rattrapage_offline.py#L92) · paramètres self
- [test_carriere_absente_ancienne_avant_enrichissement_ferrure_deja_lie](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v30_rattrapage_offline.py#L107) · paramètres self
- [test_identifiant_connu_avant_contexte_a_resoudre_sans_sauter_la_validation](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v30_rattrapage_offline.py#L121) · paramètres self
- [test_bilan_distingue_carriere_absente_et_ferrures_sans_doubler_l_identifiant](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v30_rattrapage_offline.py#L135) · paramètres self
- [test_ancienne_preuve_ne_cache_pas_une_capture_devenue_invalide](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v30_rattrapage_offline.py#L153) · paramètres self
- [test_capture_complete_datee_deja_publiee_ne_recollecte_pas](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v30_rattrapage_offline.py#L163) · paramètres self
- [test_capture_complete_absente_du_sheet_demande_uniquement_sync](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v30_rattrapage_offline.py#L171) · paramètres self
- [test_capture_plus_recente_ne_reutilise_pas_une_ancienne_preuve_sheet](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v30_rattrapage_offline.py#L176) · paramètres self
- [test_date_absente_ou_future_ne_prouve_pas_completion](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v30_rattrapage_offline.py#L192) · paramètres self
- [test_succes_checkpoint_avant_sheet_reprise_sans_recollecte_et_production_intacte](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v30_rattrapage_offline.py#L200) · paramètres self
- [checkpoint](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v30_rattrapage_offline.py#L207) · paramètres cache
- [publication](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v30_rattrapage_offline.py#L208) · paramètres horse, **kwargs
- [test_publication_echouee_reprise_sans_geny](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v30_rattrapage_offline.py#L224) · paramètres self
- [test_blocage_403_partage_avec_production_sans_contournement](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v30_rattrapage_offline.py#L234) · paramètres self
- [test_reprise_apres_expiration_et_nouveau_refus_403_429](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v30_rattrapage_offline.py#L244) · paramètres self
- [test_noms_ambigus_ne_fusionnent_pas_les_identifiants](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v30_rattrapage_offline.py#L299) · paramètres self
- [test_index_geny_local_resout_une_ancienne_course_sans_requete](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v30_rattrapage_offline.py#L308) · paramètres self
- [test_fichiers_corrompus_et_inventaire_absent_arretent_sans_reinitialiser](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v30_rattrapage_offline.py#L319) · paramètres self
- [test_moteur_rattrapage_preserve_courses_resultats_et_formules](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v30_rattrapage_offline.py#L326) · paramètres self
- [test_workflow_independant_file_distincte_et_verrou_commun](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v30_rattrapage_offline.py#L344) · paramètres self
- [test_identite_de_capture_contradictoire_n_est_pas_declaree_complete](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v30_rattrapage_offline.py#L352) · paramètres self
- [test_nom_sans_course_est_eligible_a_la_recherche_individuelle](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v30_rattrapage_offline.py#L359) · paramètres self
- [test_reprise_kpi_seule_apres_echec_sans_double_collecte](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v30_rattrapage_offline.py#L369) · paramètres self
- [test_checkpoint_git_conserve_file_production_et_recharge_reprise](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v30_rattrapage_offline.py#L383) · paramètres self
- [git](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v30_rattrapage_offline.py#L386) · paramètres *args, cwd=None
- [test_erreur_ancienne_effacee_seulement_apres_preuve_de_completion](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v30_rattrapage_offline.py#L409) · paramètres self
- [test_preuve_ancienne_ne_cache_ni_date_future_ni_identifiant_ou_url_differents](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v30_rattrapage_offline.py#L419) · paramètres self
- [test_collecteur_courant_cede_uniquement_au_cycle_pmu](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v30_rattrapage_offline.py#L432) · paramètres self
- [test_conflit_apres_completion_reouvre_la_verification](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v30_rattrapage_offline.py#L443) · paramètres self
- [test_priorite_production_termine_passage_avant_le_cheval_suivant](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v30_rattrapage_offline.py#L452) · paramètres self
- [test_priorite_verifie_les_workflows_et_cede_si_controle_indisponible](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v30_rattrapage_offline.py#L460) · paramètres self
- [test_priorite_detecte_un_cycle_pmu_queued](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v30_rattrapage_offline.py#L470) · paramètres self
- [test_courses_passees_regroupe_la_casse_et_recense_les_conflits](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v30_rattrapage_offline.py#L481) · paramètres self
- [test_formats_sheet_et_pmu_designent_un_seul_contexte](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v30_rattrapage_offline.py#L511) · paramètres self
- [test_lot_existant_conserve_deux_observations_mais_ne_collecte_qu_une_fois](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v30_rattrapage_offline.py#L519) · paramètres self
- [test_deux_courses_differentes_ne_sont_pas_des_alias_sur_le_seul_nom](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v30_rattrapage_offline.py#L544) · paramètres self
- [test_numero_absent_reste_non_resolu_si_nom_ambigu_dans_la_meme_course](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v30_rattrapage_offline.py#L553) · paramètres self
- [test_identifiant_observe_sans_url_n_est_qu_un_candidat_a_verifier](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v30_rattrapage_offline.py#L565) · paramètres self
- [test_page_candidate_exige_http_identifiant_final_et_nom](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v30_rattrapage_offline.py#L574) · paramètres self
- [test_inventaire_reconnait_une_performance_sous_sa_cle_deja_publiee](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v30_rattrapage_offline.py#L583) · paramètres self
- [test_delai_production_du_meme_cheval_respecte_dans_le_stock](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v30_rattrapage_offline.py#L600) · paramètres self
- [test_autre_contexte_du_partant_en_attente_exclu_du_fond](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v30_rattrapage_offline.py#L609) · paramètres self
- [test_creneau_libre_collecte_stock_sans_toucher_previsions_puis_cede_au_partant](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v30_rattrapage_offline.py#L619) · paramètres self
- [test_bilan_retient_le_dernier_controle_date_meme_apres_nettoyage_des_lignes](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v30_rattrapage_offline.py#L661) · paramètres self

### [tests/test_v31_dedup_offline.py](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v31_dedup_offline.py)

Imports déclarés · csv, json, pathlib, pmu_geny.controle_sync_sheets, pmu_geny.sync_google_sheets, tempfile, unittest
Point d’entrée __main__ déclaré.
- [setUp](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v31_dedup_offline.py#L14) · paramètres self
- [source](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v31_dedup_offline.py#L24) · paramètres self, rows
- [perf](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v31_dedup_offline.py#L34) · paramètres source, *, chrono="1'14''0", place='4'
- [test_url_et_description_de_la_meme_course_ne_creent_qu_une_ligne](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v31_dedup_offline.py#L39) · paramètres self
- [test_deux_courses_distinctes_meme_jour_sont_conservees](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v31_dedup_offline.py#L48) · paramètres self
- [test_persistance_et_export_fusionnes](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v31_dedup_offline.py#L55) · paramètres self
- [test_reconciliation_conserve_la_cle_anterieure](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v31_dedup_offline.py#L67) · paramètres self
- [test_cles_différentes_meme_performance_bloquees_avant_ecriture](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v31_dedup_offline.py#L76) · paramètres self

### [tests/test_v32_contextuel_offline.py](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v32_contextuel_offline.py)

Imports déclarés · datetime, json, pathlib, pmu_geny.formes_contextuelles_v32, pmu_geny.top3_independants_v22, tempfile, unittest
Point d’entrée __main__ déclaré.
- [hist](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v32_contextuel_offline.py#L20) · paramètres races, statut='COMPLET'
- [perf](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v32_contextuel_offline.py#L24) · paramètres date='2026-10-25', rang='1', distance='2700', hippodrome='Vincennes', discipline='Attelé', ferrure='D4'
- [test_musique_pas_de_confusion_monte_attele](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v32_contextuel_offline.py#L31) · paramètres self
- [test_course_identique_plus_comparable_qu_une_victoire_lointaine](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v32_contextuel_offline.py#L38) · paramètres self
- [test_allocation_inferieure_reduit_comparabilite](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v32_contextuel_offline.py#L50) · paramètres self
- [test_disqualifications_et_pas_de_reconstruction_des_ferrures](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v32_contextuel_offline.py#L59) · paramètres self
- [test_pas_de_fuite_temporelle_ni_de_melange_monte](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v32_contextuel_offline.py#L67) · paramètres self
- [test_historique_absent_musique_pmu_secours](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v32_contextuel_offline.py#L77) · paramètres self
- [test_historique_geny_sans_musique_pmu](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v32_contextuel_offline.py#L83) · paramètres self
- [test_homonyme_ambigu_interdit_historique](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v32_contextuel_offline.py#L90) · paramètres self
- [test_historique_donnees_incoherentes_rejete](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v32_contextuel_offline.py#L94) · paramètres self
- [test_pmu_geny_palimpseste_scores_sources_et_np](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v32_contextuel_offline.py#L102) · paramètres self
- [write](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v32_contextuel_offline.py#L105) · paramètres path, doc
- [test_ferrure_tierce_ignoree_meme_avec_preuve_et_heure](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v32_contextuel_offline.py#L140) · paramètres self
- [run_with](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v32_contextuel_offline.py#L141) · paramètres capture, name='Etoile', url='https://www.equidia.fr/course-test', source='equidia'
- [write](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v32_contextuel_offline.py#L144) · paramètres rel, doc
- [test_non_partant_exclu_et_pas_de_score_invente](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_v32_contextuel_offline.py#L172) · paramètres self

### [tests/test_workflows_offline.py](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_workflows_offline.py)

Imports déclarés · os, pathlib, re, subprocess, unittest, yaml
- [test_python_embarque_compile_sans_execution](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_workflows_offline.py#L12) · paramètres self
- [test_collecte_locale_sans_navigateur_au_niveau_de_l_etape_actions](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_workflows_offline.py#L25) · paramètres self
- [test_budget_nocturne_court_garde_du_temps_pour_le_fond](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_workflows_offline.py#L41) · paramètres self
- [test_declenchements_sous_le_verrou_et_sans_doublon](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_workflows_offline.py#L66) · paramètres self
- [test_rattrapage_dedie_valide_budget_et_selectionne_le_mode_selon_paris](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/blob/a4e868477423f5d15dfb332d14ee31da5cd3369b/tests/test_workflows_offline.py#L93) · paramètres self
