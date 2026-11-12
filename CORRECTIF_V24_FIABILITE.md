# Fiabilité : musique, non-partants et KPI

Premier lot issu de l'audit du 12 novembre 2026.

- Lecture des musiques PMU compactes et espacées identique ; les changements d'année sont ignorés, les places à deux chiffres et les disqualifications conservées.
- Le retrait d'un cheval actualise les TOP3 direct et marché, même si l'effectif diminue. Les retraits confirmés restent exclus si la collecte suivante ne fournit pas de statut. Seule une nouvelle confirmation explicite de participation permet une réintégration.
- Une information NP ancienne reste excluante dans la baseline historique. Une information future n'est pas utilisée. Si moins de trois chevaux restent, la dernière sélection devient indisponible.
- Les versions directes et marché remplacées sont archivées. Le nouveau moteur est identifié `direct-v24-fiabilite`. Aucune sélection passée n'est recalculée.
- Les sélections et rangs devenus vides sont effectivement effacés de leurs cellules dans Sheets ; les colonnes personnelles sont conservées.
- Les scores 0–3 sont écrits comme nombres natifs, y compris zéro, plutôt que comme textes.
- Le quatrième onglet existant `Data Quality & KPI` est désormais actualisé à chaque synchronisation, depuis les mêmes sources que les trois tables. Les indicateurs sont repérés par leur libellé ; aucune création d'onglet ni formule dépendant d'un numéro de ligne. Les arrivées, les prévisions antérieures au départ et les nombres d'historiques sont contrôlés avant comptage.
- Le contrôle Python retrouve les TOP3 historiques figés, précédemment absents de ses indicateurs en raison d'un champ non propagé.

Validation : 123 tests hors ligne réussis, dont 19 nouveaux cas métier. Sur l'instantané de référence : 13 arrivées et 13 évaluations directes, 28 participations avec historique positif, une baseline historique figée retrouvée. Ce lot corrige le fonctionnement ; il ne démontre pas une amélioration du taux de réussite futur.

Les tests réseau hippiques et les modifications de cotes, d'apprentissage ML, de cadence ou de modèle restent hors de ce premier lot. Les cotes restent exclues des variables prédictives. Les fichiers historiques et les sélections déjà publiées restent conservés.

Commande de vérification :

```sh
python -m unittest discover -s tests -p 'test_*offline.py' -q
```
