# Reprise des 31 cas restants

Les 132 historiques deja synchronises sont conserves et exclus des nouvelles consultations.

## Identification des fiches

Le collecteur cliquait au centre du `td`, alors que Geny attache la navigation au nom du cheval. Sur Illinois, la cellule mesure environ 152 pixels de large et le nom 39 pixels : le centre de la cellule est hors du controle. Le clic sur le nom exact ouvre bien la fiche `2703596-illinois/course/1698063`. La resolution attend egalement le rendu du partant et conserve les diagnostics si elle echoue.

## Mario de Lou

L'archive du premier passage contient 18 lignes pour 18 annoncees. Une ligne du 15 aout 2025, a Vittel, porte le code source `Dpg`, jusque-la non reconnu. Le parseur conserve desormais ce code tel quel. La correction de cette ligne est tracee avec sa preuve textuelle ; aucune place numerique n'est inventee. Les 18 performances passent le classifieur et sont reprises sans nouvelle requete Geny.

## Execution

La reprise utilise la meme branche et la meme sauvegarde incrementale, puis charge Google Sheets apres chaque validation. Le passage cible est borne a 75 minutes ; les cas eventuellement inaccessibles restent reprisables. Les refus 403/429 conservent leur pause globale de 30 minutes.

Validation : 134 tests hors ligne reussis ; ouverture reelle de la fiche Illinois verifiee et 18 lignes de Mario de Lou revalidees sur l'archive sauvegardee.
