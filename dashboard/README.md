# TROT Analytics
Application Streamlit indépendante, lecture seule du registre Google Sheets. Aucun appel PMU/Geny ni écriture. Aucune clé dans GitHub.

## Déploiement
1. Créer un compte de service Google Cloud dédié, activer Sheets API, partager le registre uniquement avec son adresse en **Lecteur**. Ne pas réutiliser le compte de production éditeur.
2. Créer une app sur https://share.streamlit.io : dépôt botbolmoshe-ai/pmu-geny-collecteur, branche main pour la production (feat/trot-analytics pour la recette), fichier dashboard/app.py. Choisir Python 3.12 et rendre l'application privée.
3. Dans Advanced settings > Secrets, renseigner les valeurs du modèle dashboard/secrets.example.toml depuis le compte de service. Choisir un mot de passe aléatoire d'au moins 16 caractères. Ne jamais envoyer ou commiter de clé privée.
4. Déployer, vérifier la connexion, la date, quatre écrans, un résultat et un KPI. Android Chrome > Ajouter à l'écran d'accueil.

Local : pip install -r dashboard/requirements.txt ; configurer .streamlit/secrets.toml local non versionné ; streamlit run dashboard/app.py. Tests : python -m unittest discover -s dashboard -p 'test_*.py'.

Lancer depuis la racine du dépôt pour charger `.streamlit/config.toml`.
Le conteneur de développement installe les dépendances de `dashboard/requirements.txt`
et démarre la même entrée ; ses options de prévisualisation existantes sont conservées. Les fichiers
`.streamlit/secrets.toml` sont exclus de Git. La CI installe les dépendances avant
les tests de navigation et contrôle aussi les mises à jour de main.

La date de lecture ne prouve pas la fraîcheur PMU. Matching direct issu du score enregistré validé par les preuves visibles. ML non évalué si le champ de matching de la PR dédiée manque. Aucune promesse de disponibilité continue de l'hébergement gratuit.

## Présentation de Qualité

Les indicateurs sont regroupés en sections repliables. Chaque section affiche
un tableau compact : Indicateur, Description, Nombre / valeur, Total. Le tableau
défile dans une hauteur maximale de 400 px. Le filtre de section et la recherche
dans les libellés/descriptions permettent de réduire la liste affichée.
Les totaux sont ceux de « Total de référence (automatique) », sans estimation.
Une valeur ou un total absent affiche « — » ; zéro reste affiché comme zéro.
Les taux sont présentés en pourcentage et les décimales arrondies à l'affichage.
Les données sources et les autres vues restent inchangées.

### Dates et évolution

Qualité dispose de son propre filtre de période, au format français. Choisir la
même date aux deux bornes permet un focus sur une journée.

- **Courses de la période** : indicateurs de complétude calculés depuis les
  participations des dates choisies, sur leur état actuel. Les non-partants et
  statuts à confirmer sont distingués ; les taux prennent les partants confirmés
  comme dénominateur. Les TOP3 complets reprennent les sélections stockées.
- **Relevés historiques** : valeurs vraiment conservées dans « Historique qualité ».
  Le tableau reprend le dernier relevé de la période ; la zone Évolution montre
  les différentes dates avec leurs valeurs et totaux. Un seul jour ne constitue
  pas encore une évolution. Les anciens jours sans relevé restent indisponibles.
- **Registre actuel** : conserve les KPI globaux, sans leur appliquer une fausse date.

L'onglet historique est facultatif à la lecture : son absence n'empêche pas les
autres vues. Il est alimenté par le moteur de production, jamais par l'application.
La conservation est quotidienne (dernier relevé du jour), avec heure d'observation
affichée. Les relevés en double, incohérents ou futurs ne sont pas utilisés.

### Performance

Deux barres horizontales TOP3 direct / TOP3 ML, période et hippodrome filtrables, courbes quotidiennes ou cumulées. Les deux méthodes sont comparées exclusivement sur les mêmes courses possédant deux matchings publiés et vérifiés. Les résultats manquants sont exclus, jamais convertis en zéro. Chaque course contribue au même poids ; aucun pronostic n'est recalculé et aucune écriture Sheets n'est effectuée.
