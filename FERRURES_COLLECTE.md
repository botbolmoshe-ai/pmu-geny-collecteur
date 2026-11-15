# Collecte et réparation des ferrures

## Causes constatées le 15 novembre 2026

Le collecteur de carrière Geny lisait le texte visible : les pictogrammes de
ferrure sont portés par des attributs `aria-label`, absents de ce texte. Les
14 898 performances du cache examiné n'avaient donc pas de champ `ferrure`.
Les colonnes de la Google Sheet étaient correctement associées.

Le flux PMU des partants de trot omet `deferre` lorsqu'aucun déferrage ou
plaquage n'est déclaré. Le collecteur conservait une cellule vide. Convention
recoupée sur les mêmes partants PMU du 13 novembre, R3C5, et Geny 1698194 :
Manzana Chenou et Makemyday sont explicitement FF chez Geny et sans `deferre`
chez PMU ; Midnight Oil et Manon de Busset sont FD / déferrés des postérieurs
dans les deux sources.

## Correction

- Pour chaque performance passée, lire les participations structurées Next.js
  et les libellés accessibles dans le DOM final après défilement. Vérifier
  l'identifiant, la date, le lieu, la discipline et la distance ; distinguer
  les courses multiples d'un même jour par classement et chrono. Une
  contradiction laisse la cellule non complétée et remonte un conflit.
- Traduire les codes **selon leur source**. Chez Geny : FF→F, DD→D4, DF→DA,
  FD→DP, PP→P4, PF→PA, FP→PP, PD→DP/PA et DP→DA/PP. Ne jamais interpréter
  directement un code Geny avec la table PMU.
- Pour un participant PMU complet et typé `allure=TROT`, avec identifiant et
  statut connu, l'absence de toute déclaration de ferrure devient F, avec
  provenance de cette convention. Un objet incomplet, du galop, une chaîne
  vide ou un code inconnu ne déclenchent pas ce remplacement.
- Conserver source, URL, valeur brute et date de capture. Ne pas emprunter
  la ferrure de la course actuelle pour remplir une performance ancienne.

## Reprise et suivi

Le cycle principal répare d'abord les historiques depuis les HTML déjà
sauvegardés : aucune requête Geny supplémentaire. Les versions précédentes
sont archivées, les CSV régénérés et la date originale de capture conservée.
Les partants PMU incomplets sont relus depuis leur course d'origine ; seuls
les champs ferrure manquants d'une identité concordante sont enrichis. Une
erreur 403/429 interrompt cette reprise, sans contournement. Les fichiers
encore incomplets ne sont pas relus avant six heures.

Les deux reprises passent par le moteur Sheets commun et ses contrôles
antidoublons. Les cellules existantes sont mises à jour sans nouvelle ligne
pour la même performance. Les pronostics figés et instantanés d'entraînement
ne sont pas réécrits par la réparation.

Chaque historique expose `ferrures_renseignees`, `ferrures_manquantes` et
`ferrures_statut`. Une carrière complète avec des ferrures manquantes reste
à enrichir dans les collecteurs existants ; le rattrapage ne peut plus se
déclarer terminé dans ce cas. Le bilan expose
`historiques_ferrures_a_completer`. Les pauses de source sont conservées.

## Vérification initiale sur une copie réelle

48 archives exploitables : 42 historiques enrichis, 1 091 ferrures récupérées,
aucun conflit. Deuxième passage : zéro ajout. Relecture officielle de
95 courses PMU : 433 ferrures supplémentaires, aucune erreur HTTP. Ces
chiffres décrivent la validation locale ; les journaux du cycle de production
font foi pour la publication réelle.

Tests : tables propres aux sources, identité et courses multiples, absence
de fausse imputation, conservation d'une ferrure connue, régression bloquée,
reprise reproductible, respect du 429, mise à jour d'une cellule existante
sans doublon et compilation du Python intégré aux workflows.
