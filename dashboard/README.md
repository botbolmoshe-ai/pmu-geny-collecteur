# TROT Analytics
Application Streamlit indépendante, lecture seule du registre Google Sheets. Aucun appel PMU/Geny ni écriture. Aucune clé dans GitHub.

## Déploiement
1. Créer un compte de service Google Cloud dédié, activer Sheets API, partager le registre uniquement avec son adresse en **Lecteur**. Ne pas réutiliser le compte de production éditeur.
2. Créer une app sur https://share.streamlit.io : dépôt botbolmoshe-ai/pmu-geny-collecteur, branche feat/trot-analytics pour recette (main après fusion), fichier dashboard/app.py. Choisir Python 3.12 et rendre l'application privée.
3. Dans Advanced settings > Secrets, renseigner les valeurs du modèle dashboard/secrets.example.toml depuis le compte de service. Choisir un mot de passe aléatoire d'au moins 16 caractères. Ne jamais envoyer ou commiter de clé privée.
4. Déployer, vérifier la connexion, la date, quatre écrans, un résultat et un KPI. Android Chrome > Ajouter à l'écran d'accueil.

Local : pip install -r dashboard/requirements.txt ; configurer .streamlit/secrets.toml local non versionné ; streamlit run dashboard/app.py. Tests : python -m unittest discover -s dashboard -p 'test_*.py'.

La date de lecture ne prouve pas la fraîcheur PMU. Matching direct issu du score enregistré validé par les preuves visibles. ML non évalué si le champ de matching de la PR dédiée manque. Aucune promesse de disponibilité continue de l'hébergement gratuit.
