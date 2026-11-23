# PMU — Doctrine d'audit et apprentissage des erreurs (V20.1)

## Règle non négociable
La cote, le rang des favoris du marché et les rapports PMU sont **interdits comme variables d'entrée de la baseline et du modèle ML**. Ils sont conservés **uniquement pour comparaison après course**. Aucune fonctionnalité, même indirecte (score de consensus, rang du marché, variable issue d'un modèle entraîné sur les cotes), ne peut réintroduire cette information dans les prédictions.

## Quatre référentiels distincts
1. Baseline H-2 immuable, horodatée avant le départ. Les références historiques H-1 gardent leur libellé.
2. Baseline finale corrigée des non-partants, horodatée et versionnée.
3. Machine Learning, produit avant le départ, avec statut de disponibilité.
4. Marché : cotes horodatées, relevées avant le départ, sans garantie de cote définitive. L'absence de cote doit rester visible.

## Audit après course
Uniquement après arrivée officielle vérifiée : nombre de chevaux du podium réel retrouvés par chaque méthode (0–3), outsiders correctement détectés, outsiders manqués, favoris du marché que notre ML n'avait pas identifiés. Le rang des cotes n'est qu'un indicateur et **ne prouve ni probabilité juste ni causalité**. Les comparaisons interméthodes exigent une couverture suffisante et des données pré-départ.

## Autocritique, sans surapprentissage
Chercher les écarts récurrents par hippodrome, distance, âge, forme 30/60/120 jours, repos, niveau d'opposition, driver, entraîneur, ferrure, météo, piste, bruit d'écurie **sourcé**. Signaler les données manquantes, dégradations et divergences du marché. Ne jamais convertir des rumeurs en diagnostic de santé confirmé.

Ne jamais modifier les pondérations sur une seule course. Pour toute modification : hypothèse documentée, nombre de cas, comparaison temporelle hors-échantillon sur les **mêmes courses**, métriques TOP3 et calibration, décision de maintien/retour arrière. Évaluer la capacité à trouver les outsiders **sans sacrifier** la performance globale. Les prises de décision sur les paris nécessitent une évaluation distincte des rapports et de la rentabilité réelle.

## Artefacts
- `audits/AAAA-MM-JJ_RxCy.json` : audit par course, chevaux et écarts.
- `audits/bilan_comparatif.csv` : suivi longitudinal baseline / ML / marché.
- `exports/<GENY-ID>/comparatif_predictions.csv` : comparatif existant par cheval.

Le module d'audit est strictement descriptif : **il ne réentraîne pas et ne modifie aucun modèle**. L'entraînement futur devra prendre en compte les enseignements uniquement après validation statistique.
