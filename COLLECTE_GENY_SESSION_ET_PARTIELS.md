# Collecte des prochains partants : continuité et données partielles

## Diagnostic du 16 novembre 2026

Les passages 43962802213 (21:43 UTC) et 43968761756 (22:19 UTC) ont chacun
effectué une tentative et validé zéro historique. Le registre source conserve
un refus explicite HTTP 403 ; les refus 429 étaient également présents avant
ce changement. Ce constat ne prouve pas une déconnexion d'un compte utilisateur.
La collecte publique n'effectue aucune connexion à un compte Geny.

Sur la copie examinée : 675 carrières sauvegardées, 18 497 performances sources
Geny et 103 partants du lendemain sans identité Geny déjà associée. Le contrôle
des prochains départs autorisait les 103 profils PMU ; il n'explique pas leur
refus d'accès. Les anciennes lignes Sheets incluent aussi des données héritées.

## Corrections

- Le même navigateur et le même contexte servent à résoudre la fiche et lire
  la carrière. Une fiche ouverte par le clic est lue directement : pas de
  deuxième chargement de cette fiche, ni de perte des cookies entre ces étapes.
- Un lien résolu est sauvegardé avant extraction, repris après interruption et
  mémorisé par la file. Une panne réseau ne l'efface plus systématiquement.
- Les lignes d'une carrière partielle peuvent être conservées séparément dans
  `historiques_partiels/ID/historique_geny.json`. Identité, hôte, ID, date de
  capture, dates de course, champs essentiels et doublons restent contrôlés.
  Ces fichiers ne remplacent jamais une carrière complète ; une capture partielle
  remplacée est archivée avec son horodatage source.
- Les lignes valides passent par le moteur Sheets existant, avec le statut
  `EXTRACTION_GENY_PARTIELLE`. Le partant indique `HISTO_PARTIEL_GENY`. La liaison
  des chevaux et les futures captures ML peuvent utiliser ces données ; les
  compteurs distinguent complet et partiel, et la reprise complète reste due.
- Les instantanés et prévisions déjà gelés ne sont pas réécrits. Le verrou
  commun, la priorité aux prochaines courses et les pauses 403/429 subsistent.

Une interruption de la conversation n'arrête pas les workflows GitHub Actions.
Un arrêt du worker reprend à partir du checkpoint durable.

## Validation

`python -m unittest discover -s tests -p 'test_*.py' -q` : 338 tests réussis.

`python -m scripts.valider_session_geny_hors_ligne` vérifie aussi le navigateur
réel avec des pages simulées et toutes les requêtes interceptées : deux
navigations (course puis cheval), cookie conservé, fiche chargée une fois,
une performance extraite sur deux annoncées et carrière correctement partielle.
Le test de publication vérifie ensuite le passage partiel → complet sans
réinsérer la performance. Sur la copie de production, les 18 497 performances
sources restent identiques et continuent d'être qualifiées Geny complètes.

## Limite et solution de repli

Les performances partielles vérifiées et les historiques déjà sauvegardés
permettent de travailler sans attendre une carrière exhaustive. En l'absence
de données Geny exploitables, la forme PMU reste le secours existant. Aucune de
ces solutions ne reconstitue les courses manquantes ni ne promet une carrière
complète en présence d'un refus Geny. Les imports de diagnostics archivés
restent utilisables pour retraiter une capture existante sans requête Geny.
