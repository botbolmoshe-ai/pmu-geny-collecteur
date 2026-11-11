# PMU V21 — Intégration et contrôles (11 novembre 2026)

Workflow principal unique : **PMU - V21 - Rapprochement PMU Geny et tableau de bord**.
Le chemin historique `.github/workflows/pmu-v16.yml` est conservé pour ne pas ajouter une seconde chaîne planifiée.

## Modifications V21

- Collecte historique Geny : espacement de **30 secondes** entre nouvelles fiches (ne garantit pas l'absence de limitation).
- Après découverte d'un manifeste, **pas de collecte historique sur le même cycle**. L'exécution suivante réutilise le manifeste persisté dans `pmu-data`.
- Validation Geny : plusieurs performances sur la même date et le même hippodrome sont autorisées si les lignes sources diffèrent ; les lignes identiques sont refusées.
- Les valeurs de classement `D` et `R` sont conservées telles qu'affichées, sans les convertir en positions numériques. Signification métier de `R` encore à documenter.
- Programme PMU : **départs 08 h 00 à 19 h 00 inclus**, heure Europe/Paris. La fenêtre jusqu'à 20 h 59 sert au traitement post-course et à la préparation autorisée de J+1.
- Google Sheets / historique : conservation de plusieurs performances distinctes pour un même cheval, une même date et un même hippodrome ; conservation de la clé historique de la première occurrence et suffixe stable pour les suivantes.
- Aucun changement du moteur de scoring/ML. Les non-partants et TOP3 restent soumis à leurs contrôles actuels.

## Preuves disponibles

- 12 novembre, Vincennes R1C1 : **17/17 historiques validés**, 465 performances annoncées et extraites au total, sur plusieurs exécutions isolées.
- Correction hors ligne de Frank Gio : deux performances distinctes à Naples le 03/05/2026 conservées.
- Corrections hors ligne Magic Night (code R) et Liza Josselyn (code D) validées.
- Test initial de rapprochement : **11/13 associations confirmées**, deux groupes de la Coupe des Amateurs encore sans correspondance fiable.

## Validations requises avant toute conclusion de fiabilité globale

1. Lancer `.github/workflows/verification-v21.yml` : syntaxe + suite de tests hors ligne, aucun accès réseau aux sites hippiques.
2. Lancer `.github/workflows/audit-generique-integre.yml` : examiner l'état durable `pmu-data` sans écriture.
3. Observer un cycle réel V21 : PMU -> rapprochement -> manifeste -> reprise au cycle suivant -> historique -> TOP3 -> arrivée -> bilan -> Sheets. **Un statut GitHub Success seul ne démontre pas la réussite fonctionnelle de toutes les étapes.**
4. Reprendre de manière contrôlée les 17 historiques conservés dans les artefacts de test ; ils **ne figurent pas encore** dans `pmu-data`.

## Écarts résiduels connus

- Les règles P1/P2 filtrent actuellement les courses, au-delà du seul périmètre « trot France, 08–19 h » : il faut valider explicitement la stratégie d'exhaustivité ou de priorité.
- Le rapprochement PMU–Geny n'a pas atteint 100 % sur le test du 12 novembre.
- Le tableau de bord historique conserve certaines anciennes clés : une revue des lignes déjà présentes est nécessaire avant toute opération de nettoyage ou migration.
- La récupération systématique des arrivées et la complétude des bilans/Top3 ne sont pas démontrées par les tests d'historiques.
- Aucune preuve de trois sources d'avis experts ni d'entraîneur/driver n'est fournie par cette V21 ; ne pas afficher ces indicateurs comme collectés.

**Conservation** : pas d'effacement de données historiques et aucun processus de test ne doit écrire dans `pmu-data` ou Google Sheets.

## Reprise finale contrôlée des 17 historiques

Un workflow manuel `.github/workflows/reprise-historiques-v21.yml` permet de reprendre les cinq artefacts de test sans nouvelle requête Geny. Deux modes : `verifier` (simulation sans écriture) et `importer` (validation obligatoire des **17 historiques et 465 performances**, puis écriture atomique des fichiers de chaque cheval dans `pmu-data`, conservation des historiques complets antérieurs, mise à jour du journal et audit du registre).

L'opération utilise le même verrou de concurrence que la production. Le contenu des artefacts est validé avant toute écriture, et les écarts font échouer l'exécution. L'import ne crée pas un manifeste de course artificiel, n'efface rien et ne contacte pas Geny. Les trois historiques incomplets du registre (2905469, 2907579, 2907581 : zéro performance extraite, nombre annoncé inconnu) **ne peuvent pas être réparés avec ces artefacts** ; ils restent à diagnostiquer séparément.
