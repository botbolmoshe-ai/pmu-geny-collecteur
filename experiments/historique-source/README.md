# Banc d'essai historique — PMU

Branche expérimentale isolée de `main` : aucun déclenchement de production.

## Hypothèse à tester

La source PMU (https://www.pmu.fr/) permet-elle d'extraire, sans contournement de contrôle d'accès, les performances antérieures d'un cheval identifié par son **nom normalisé** et, si disponible, son **identifiant propre à la source** ?

## Protocole de validation

1. Échantillon fixe de chevaux déjà rencontrés : historique disponible, partiel, absent et homonymes.
2. Vérifier l'accessibilité publique et les conditions d'utilisation avant toute collecte automatisée.
3. Extraire les performances : date, hippodrome, discipline, distance, classement, partants, driver, entraîneur, ferrure, URL de preuve.
4. Normaliser le nom en majuscules pour le rapprochement, mais ne jamais utiliser le numéro de partant comme identifiant stable.
5. Mesurer : fiches accessibles / testées, performances par cheval, proportion de ferrures renseignées, concordance PMU, temps par fiche, erreurs 403/429/404, doublons.
6. Comparer à Geny sur **le même échantillon** ; conserver les données brutes et leur provenance.
7. Aucun déploiement, fusion ou écriture dans le registre de production avant validation documentée.

**État :** branche et protocole créés ; extraction réelle et taux de réussite non encore mesurés.
