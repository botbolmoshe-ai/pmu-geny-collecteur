# TOP3, ML actif et historiques : corrections du 17 novembre 2026

## Causes constatées

Le dernier cycle de nuit précédait 07 h Paris. La règle de décision 07 h–21 h
empêchait les premières prévisions du jour. Le worker attendait en plus un TOP3
pour enrichir les historiques de ces mêmes courses : les partants du jour
étaient donc délaissés au profit du lendemain. Une insuffisance de données de
classement pouvait également entretenir cette dépendance circulaire.

Le ML expérimental avait bien appris et été évalué sur les données admissibles,
mais aucun candidat actif n'alimentait l'inférence en l'absence de promotion.
Le fichier affichait seulement ML_NON_ENTRAINE pour le modèle de production.

La collecte n'était pas arrêtée : le registre est passé de 675 à 722 chevaux
pendant la nuit ; le dernier passage examiné a validé 12 captures. Le rattrapage
de fond restait légitimement différé au profit des prochains partants.

## Fonctionnement corrigé

- TOP3 préliminaires dès le début du jour J si les données suffisent. Le jour
  suivant reste en préparation ; aucune sélection rétrospective n'est créée.
- Les profils PMU frais et identifiés autorisent l'enrichissement Geny même sans TOP3 ou critère facultatif renseigné.
  L'absence de prévision reste visible et bloque la reprise du stock ancien.
- À départ identique, une carrière absente passe avant une vérification de
  carrière déjà disponible. La couverture est comptée par date de course et
  recalculée à la fin du worker, distinctement du stock historique global.
- Le temps réel est revérifié après les appels réseau et avant sauvegarde :
  franchir le départ pendant un calcul ne produit pas de prévision tardive.
- Le candidat ML actif apprend sur toutes les observations pré-départ avec
  arrivées déjà disponibles, sans les seuils de promotion 100 courses/700 lignes
  ni l'attente de 20 h. Les valeurs manquantes passent par l'imputation du même
  moteur statistique. Il faut des classes positives et négatives et au moins
  une variable exploitable ; aucune étiquette n'est inventée.
- Les définitions de modèles sont partagées avec l'expérience temporelle. Le
  candidat est conservé dans ml/modeles_experimentaux, référencé et vérifié par
  SHA256, sans écraser ml/modele.joblib. Données admissibles inchangées : pas
  de nouveau fit. Un fichier corrompu est réentraîné.
- Le candidat est préparé avant le cycle PMU ; l'évaluation et le contrôle de
  promotion restent exécutés après les arrivées. Le modèle promu garde la
  priorité. À défaut, l'inférence porte explicitement le statut
  ML_EXPERIMENTAL_ENTRAINE_NON_CALIBRE et promotion_production=false.
- Les huit sélections expérimentales peuvent être publiées avant les courses,
  avec scores non calibrés, identifiant du modèle et entrées exactes. Les mises
  à jour sont versionnées. Les anciens instantanés ne sont pas réécrits.
- Cinq indicateurs KPI rendent visibles le statut expérimental, le nombre de
  courses et observations apprises, la date du fit et celle de vérification.
  Aucune colonne supprimée lors du nettoyage n'est recréée.

## Vérifications avant déploiement

358 tests passent, dont l'apprentissage avec une seule période admissible,
les variables manquantes, la réutilisation du modèle sans nouveaux labels,
le refus des labels futurs, le contrôle d'intégrité, les NP, les courses déjà
parties et le franchissement du départ pendant le calcul. Un test intégré
reproduit le cycle nocturne PMU → TOP3 → file d'historiques.

Sur copie de production : fit effectif sur 78 courses / 1 052 observations,
huit TOP3 ML calculés pour le 17 novembre, aucune promotion et aucun instantané
existant modifié. Le réentraînement sur toutes les données utilise également
l'ancien jour test ; les anciens scores rétrospectifs ne constituent donc PAS
une nouvelle mesure indépendante de ce candidat. Sa performance doit être
mesurée sur les prévisions futures effectivement enregistrées avant départ.

## Exploitation

Le verrou commun, les checkpoints avant Sheets, les contrôles de doublons et
les pauses 403/429 restent en place. Les jobs success ne suffisent pas à déclarer
la complétude : vérifier les fichiers de pronostic et leurs heures, le modèle
et son rapport de fit, la publication et les captures réellement acceptées.

Les versions prédictives présentes font autorité, y compris leurs champs vides :
un retrait ou une sélection invalidée efface les anciens rangs/scores affichés.
La correction complémentaire de préparation/publication est intégrée au même
chemin, avec ses tests de fraîcheur et de retrait.
