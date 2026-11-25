# Restitution des résultats PMU — complément du ticket 127

Contrôle en lecture du checkpoint `pmu-data@198eea531` du 24 novembre 2026.
Les rapprochements préexistants ont un dictionnaire de scores vide sur les
cinq courses signalées. La restitution relit la paire H2 dans les archives
durables, vérifie la relecture Sheets, l'empreinte de la version, l'heure de
publication et le départ. Elle ne recalcule aucun pronostic.

| Course | Constat sur la preuve H2 | Matching ML de restitution |
| --- | --- | ---: |
| R3C6 | Départ enregistré différent du départ de la version archivée | Non évaluable |
| R3C7 | Départ enregistré différent du départ de la version archivée | Non évaluable |
| R3C8 | Départ enregistré différent du départ de la version archivée | Non évaluable |
| R4C1 | Paire Direct et ML retrouvée et validée | 2/3, soit 66,67 % |
| R4C3 | Paire Direct et ML retrouvée et validée | 1/3, soit 33,33 % |

La publication prend la paire H2 en priorité et utilise une paire complète
H3 ou H1 en secours. Cette règle remplace la priorité historique donnée à
H1 dans la restitution quand les deux paires sont disponibles. Les preuves
et versions individuelles restent dans `jalons` et `publications`.
Le calcul ML et la raison d'une évaluation manquante sont exposés au tableau
de bord. Les données/états par jalon restent disponibles pour la supervision
et les tests, même lorsqu'ils sont retirés de la table utilisateur.

## Migration à qualifier avant déploiement

Le moteur Sheets lit les en-têtes normalisés et republie le périmètre à partir
de `REPORT_COLUMNS`. Le dashboard lit les champs de comparaison et le KPI
exploite les archives séparées de rapprochement. La migration existante des
dates a ajouté des colonnes d'affichage Paris dans plusieurs onglets.
Une suppression de colonnes doit couvrir également les usages non versionnés
de Google Sheets (formules, plages et vues), avec sauvegarde, test sur copie,
contrôle du différentiel avant/après et second passage sans mutation. Ce
complément prépare la restitution et les règles de preuve. Il ne modifie
aucune colonne en production.

Le planificateur en lecture seule a reconnu 16 colonnes par jalon parmi
les 53 en-têtes réels de Résultats & Analyse (`AG:AR` et `AX:BA` au moment
de l'audit). Il conserve 37 en-têtes, dont la clé, les scores synthétiques,
les heures de référence et le jalon comparé. Les 12 formules lues dans
Data Quality & KPI ne référencent pas directement Résultats & Analyse.
Cela ne couvre pas les pivots, les vues, les autres formules du classeur
ni les consommateurs externes. Le planificateur ne produit aucune requête
d'écriture et le contrôle avant/après conserve notamment les zéros valides.

```bash
python -m pmu_geny.plan_retrait_resultats entetes-resultats.json
```

Une lecture complète en mode FORMULA n'a trouvé aucune formule dans Résultats
& Analyse ni dans TCD. Le pivot inspecté dans TCD lit Historique chevaux
(onglet 810003). L'essai hors ligne de retrait contrôle l'ordre sauvegarde,
relecture avant écriture, mutation ciblée, puis contrôle des valeurs restantes.
Il refuse une modification concurrente et le second passage ne produit aucune
écriture.

Le producteur publie la synthèse sans recréer les en-têtes H1/H2/H3 retirés.
Il reste compatible avec les registres qui les possèdent encore. La relecture
certifie les champs synthétiques et les détails lorsqu'ils existent. Les
preuves et métriques par jalon restent dans les données d'archive.
Le mécanisme d'application reste sans point d'entrée production jusqu'à la
répétition sur une copie sauvegardée et au contrôle des consommateurs.


## Vérification complémentaire de Vincennes

Le commit public `pmu-data@e484fa15` conserve le programme consulté avant
l'établissement des TOP3 de Vincennes R3 le 24 novembre. Pour R3C6, R3C7
et R3C8, l'hippodrome, le libellé, la discipline et la distance concordent
avec le programme final. Les deux versions H2 et leur publication précèdent
l'horaire annoncé et l'horaire final. Le rapprochement peut donc réutiliser
les paires Direct/ML et les arrivées déjà vérifiées. La référence initiale
et les fichiers figés restent les preuves de ce qui a été publié.
