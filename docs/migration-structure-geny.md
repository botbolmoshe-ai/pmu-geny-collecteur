# Historiques Geny structurés

Le parseur version 1 utilise les lignes déjà collectées et les archives de
production. La colonne historique `source_url` conserve son rôle de
compatibilité. Les nouvelles colonnes `Geny · Texte brut` et `Geny · URL source`
distinguent le contenu de sa provenance. `Auto`, les codes de piste et les
libellés de terrain sont conservés tels qu'observés. Un tiret laisse le mode de
départ vide. Les cotes sont informatives. Les champs structurés sont affichés en
italique dans Sheets et Streamlit.

Le workflow manuel « Geny - migration historique du registre » utilise le
verrou `pmu-donnees-production`. Par défaut, il inventorie les cellules et
archive un instantané chiffré. Avec `appliquer=true`, il relit l'instantané avant
écriture, complète les seules cellules vides des nouvelles colonnes, puis
vérifie les valeurs et les clés par deux lectures. Les clés répétées sont
ignorées et comptabilisées. Un second passage sur les mêmes données doit
planifier zéro cellule. Les cycles habituels alimentent les nouvelles colonnes
dès qu'elles existent.

La sauvegarde contient les valeurs et expressions du seul onglet historique.
`cle.rsa` enveloppe une clé AES-256-GCM avec RSA-OAEP SHA-256 (MGF1 SHA-256,
label vide) sous la clé publique du compte de service. `historique.aesgcm`
contient le nonce de 12 octets suivi du texte chiffré et du tag d'intégrité.
La clé privée correspondant à celle du jour de la sauvegarde est nécessaire
à la récupération. Le fichier `sha256` vérifie le document JSON déchiffré.

La mesure hors réseau sur `pmu-data@3553188` a trouvé 31 810 performances dans
la source de publication, dont 31 747 cordes et 22 473 chronos lisibles. Le
rapport de migration mesure séparément la couverture réellement relue dans
Sheets. Les données extraites restent hors des variables du modèle.
