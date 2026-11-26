# Collecte Geny – ticket #134

## Référence de production

Le passage [45745117528](https://github.com/botbolmoshe-ai/pmu-geny-collecteur/actions/runs/45745117528) du 26 novembre 2026 a produit 9 carrières validées et relues dans Sheets, 459 performances ajoutées et 550 requêtes Geny, soit 61,1 par carrière et 1,20 par performance ajoutée. Aucun 403/429 n’a été relevé. Les journaux montrent sept minutes consommées par la file prioritaire et sept minutes attribuées au fond. La passe de fond a progressé, puis s’est arrêtée sur le budget temps. Le snapshot `pmu-data` `82e2ac2` inclut des checkpoints incrémentaux plus récents que celui du fond, resté à 03:06 UTC.

Le code de référence comptait toute ressource Geny dans un seul total, sans ventilation par type, URL ou cache. Les neuf ouvertures de carrière du passage étaient des variantes contextualisées par course. Chaque tâche lançait un Chromium avec un profil neuf, qui retéléchargeait les scripts statiques communs. Une fiche canonique lue en HTTP simple a retourné 200 après résolution de sa redirection 308. Son HTML a annoncé 22 courses, mais le parseur de carrière n’a validé aucune ligne à partir du texte HTML seul. Un script commun référencé par cette fiche avait un `Cache-Control: public, max-age=31536000, immutable`. La mesure hors ligne confirme le coût reproductible des scripts, avec les limites indiquées ci-dessous.

## Entrées et simplification

| Entrée | Chemin conservé |
|---|---|
| Production PMU | Les sources PMU et les jalons établis restent prioritaires. L’index quotidien Geny après publication reste une aide au rapprochement. |
| Historiques incrémentaux et rattrapage | Les deux files appellent le même worker, avec checkpoint avant publication, validation Sheets et reprise de synchronisation sans nouvelle extraction. |
| Résolution par course | Lecture unique du tableau et des données structurées. La file de reprise conserve le résultat du pilote, admet les nouvelles courses éligibles et respecte le refroidissement partagé. |
| Mode manuel de découverte | Le manifeste s’appuie sur la même extraction de preuves depuis la page de la course. Les clics et allers-retours par fiche ont été supprimés. |
| Lecteurs et migrations legacy | Les diagnostics archivés, les preuves de clic historiques et les registres de correspondance restent lisibles. Les utilitaires historiques encore couverts par les tests restent disponibles. |

Le worker partage le profil Chromium éphémère entre tâches d’un même passage. Il ouvre la fiche canonique, ferme les onglets avant le prochain démarrage et mesure séparément les événements navigateur, les ressources servies du cache et les appels réseau. Le parseur conserve la vérification du total Geny, des identités, des rangs et des ferrures. Le défilement dépend de la stabilisation de la page et du budget technique. Le plafond de dix courses du pilote et la limite manuelle implicite de 18 chevaux ont été retirés. Les fenêtres PMU, la cadence inter-chevaux et les pauses 403/429 restent appliquées.

IndexGeny et les files durables existantes portent les preuves. L’identifiant PMU, la concordance du nom, l’année et le contexte de course départagent les candidats lorsque ces informations existent. Les 801 contextes de référence se répartissent en 745 avec course et 56 sans course, soit 797 noms distincts. Aucun ne porte d’échec de collecte individuel dans ce snapshot. En relecture locale, 2 liens étaient disponibles pour les 801 contextes et aucun pour un échantillon déterministe de 30 contextes, moitié avec course et moitié sans course. Le lot fixe est à 76/96 publiés. Les vingt restants avaient tous un identifiant et une carrière absente, partielle ou non datée à reprendre. Aucun ne portait d’échec individuel dans le checkpoint. La liste de 96 et l’alias de Jiska de Dream sont conservés.

[Les règles publiques de Geny](https://www.geny.com/robots.txt) excluent la recherche interne automatisée et les variantes de fiches rattachées à une course. La voie nominative en ligne est désactivée par défaut, avec état et motif explicites quand cette restriction bloque le rapprochement. Elle requiert une autorisation explicite de Geny avant activation. Les correspondances préexistantes sont recherchées par nom dans les preuves et archives locales.

## Registre et recette

Une colonne permet le filtrage et la couleur des cinq états. Les notes conservent le motif et les horodatages disponibles. Le moteur vérifie la valeur relue dans Sheets. Streamlit affiche le même état dans le tableau, le filtre et la fiche cheval. Les indicateurs affichent un dénominateur distinct, avec l’identifiant PMU ou Geny quand il est disponible et une approximation nom–âge sinon. La liste de détail présente les engagements visibles.

Sur le snapshot `82e2ac2`, les projections avant/après ont produit les mêmes 3 325 lignes cheval-course, 246 résultats et 36 872 lignes historiques. Les empreintes des historiques, des champs de prévision et des résultats hors heure de synchronisation sont identiques. Les 3 325 statuts projetés se répartissent en 1 409 confirmés, 1 915 sans recherche attestée et 1 non trouvé sur tentative archivée.

La recette Chromium se rejoue avec `python -m scripts.mesurer_cache_geny_hors_ligne --source reference_pmu`. Le serveur local sert les chemins de scripts présents dans les captures avec la directive de cache observée sur Geny. Sur 30 carrières et 840 performances, les requêtes sont passées de 1 340 à 111 (−91,7 %), dont les scripts de 1 250 à 51. Le temps local est passé de 29,01 s à 45,82 s, le serveur local rendant la latence réseau négligeable. Le test compare chaque carrière complète, y compris ses ferrures extraites, sur le texte et le HTML archivés. Il ne rejoue pas le JavaScript distant ni les temps de réponse Geny.

## Publication et retour arrière

Les workflows de validation existants couvrent le moteur et le dashboard. La coordination avec #127 conserve le verrou partagé et les conditions d’ordonnancement. Relever la référence des nouvelles actions, les checkpoints et la pause Geny avant toute collecte de production. Relire ensuite les en-têtes, les statuts et les KPI dans le registre, puis les mêmes lignes dans Streamlit. Le ticket #134 peut être clôturé après ces contrôles et la vérification terrain des nouveaux appels et des historiques publiés.

En cas d’échec de production, interrompre la reprise Geny et revenir au commit précédent sur `main` par un revert. Les archives `pmu-data` gardent les captures et les preuves validées. La colonne et les KPI ajoutés doivent être rapprochés des écritures observées avant toute correction du registre.
