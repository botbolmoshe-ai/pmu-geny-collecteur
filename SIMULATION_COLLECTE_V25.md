# Simulation de la collecte et du remplissage — 12 novembre 2026

## Résultat

Trois gains distincts sont mesurés : la correction de musique classe tous les chevaux éligibles du rejeu, une correction supplémentaire évite de gaspiller le quota historique, et un correctif de présentation réutilise des arrivées déjà stockées. La simulation ne démontre pas que Geny fournira toutes les fiches ni qu'un modèle est désormais fiable.

| Contrôle | Avant | Après, en simulation |
|---|---:|---:|
| Chevaux éligibles avec score, archives des 13 courses du 12 novembre | 164/180 | 180/180 |
| Chevaux du podium retrouvés, même rejeu technique | 10 | 11 |
| Nouveaux historiques simulés, première course entièrement en cache, quota 6 | 0 | 6 |
| Nouveaux historiques simulés, première course ayant seulement 3 fiches à récupérer, quota 6 | 3 | 6 |
| Rangs d'arrivée transférés vers les lignes de partants, sans nouvelle requête | 50 | 134 |
| Lignes avec sélection directe explicitement renseignée, registre jour J et J+1 | 69/318 | 318/318 |

« Historiques simulés » désigne la réponse contrôlée d'un extracteur de test. Aucun de ces six historiques n'est présenté comme une nouvelle collecte réelle. L'arrêt après un refus 429 reste respecté : une tentative, aucune récupération, aucun appel supplémentaire dans le cycle. Le plafond reste fixé à six consultations, partagées entre les courses.

## Rejeu des classements

Le test emploie les pages Equidia déjà sauvegardées avec un horodatage antérieur au départ, en contrôlant date, hippodrome, titre, nom et numéro du cheval. Les seuls champs utilisés dans le score sont les performances de la musique ; aucune cote, note éditoriale ou arrivée de la page n'est utilisée. Les résultats PMU sauvegardés sont joints après calcul pour compter les intersections avec le podium.

Le parseur précédent et le parseur corrigé reçoivent exactement les mêmes musiques. La comparaison porte sur **13 courses, 183 déclarations et 180 chevaux non retirés à l'instant de l'archive**. Elle n'est pas une reconstruction exacte de chaque pronostic publié : les sources et instants peuvent différer du dernier relevé PMU de production.

La couverture progresse de 91,1 % à 100 %. Les 16 chevaux auparavant privés de score deviennent classables. Le score total passe de 10 à 11 chevaux du podium retrouvés, soit environ 0,77 à 0,85 par course. Certaines courses s'améliorent et d'autres se dégradent : c'est un contrôle technique rétrospectif, pas une validation indépendante ni une garantie de progrès futur.

## Pourquoi la collecte historique gaspille son quota

L'orchestrateur attribue un quota à une course, puis le soustrait intégralement même si son collecteur n'a fait aucune nouvelle consultation. Un premier manifeste entièrement en cache peut ainsi consommer six unités fictives et empêcher de servir le manifeste suivant.

Le correctif préparé fait remonter le nombre de tentatives réellement exécutées et celui des historiques réutilisés. Seules les tentatives consomment le budget ; les erreurs et refus comptent aussi. La simulation traverse l'orchestrateur et le collecteur réels, avec l'extracteur réseau remplacé par une réponse contrôlée et les autres accès réseau interdits.

Deux cas reproduisent le gaspillage :

- Première course déjà complète : ancien code = 0 nouvelle tentative ; correctif = 6 tentatives sur la suivante.
- Première course ayant seulement trois historiques manquants : ancien code = 3 tentatives au total ; correctif = 3 puis 3, sur deux courses.

Cela rend le budget utile mais n'augmente ni le plafond ni les droits d'accès au site.

## Contrôle réel limité de l'accès

Une seule URL déjà présente dans un manifeste du lendemain a été consultée : Le Trésor Kraailo, identifiant 2813947, course Geny 1698190. Le serveur a renvoyé **HTTP 404**, à 21 h 49 UTC. Aucun nouvel historique n'a été extrait. Ce contrôle ne mesure pas le taux d'échec global du site ; il démontre qu'au moins une fiche planifiée échoue aussi pour une raison d'accès ou d'URL, au-delà du problème de quota. Les erreurs 403/429 déjà présentes dans les journaux constituent un problème distinct.

Avant toute hausse de cadence, vérifier cette URL par rapport au lien actuellement publié sur la source, classer les erreurs par cause et éviter les reprises aveugles des liens invalides. Une réponse 404 ne doit pas être assimilée à une absence de performances du cheval.

## Pourquoi certaines cellules sont vides

Le registre de référence contient **318 participations**, dont des courses du lendemain. Il ne faut pas attendre une arrivée pour une course encore future, ni un rang numérique pour un non-partant ou un cheval non classé.

| Donnée | Renseignée dans le registre de référence | Lecture |
|---|---:|---|
| Driver, entraîneur, âge, sexe, gains | 318/318 chacun | Collecte disponible |
| Ferrure | 233/318 | 85 absences de donnée explicite ; ne pas transformer automatiquement en « ferré » |
| Rang direct actuellement sauvegardé | 286/318 | Certaines anciennes musiques ne produisaient pas de score ; retraits et versions à distinguer |
| Historique rattaché au partant | 28/318 | 290 participations sans historique collecté |
| Cote extraite | 0/318 | Extracteur de cotes encore à corriger séparément |
| Rang ML | 0/318 | Aucun modèle entraîné ; ce classement ne peut pas être inventé |

Dans une course, seuls trois chevaux sont sélectionnés, mais tous les chevaux classables peuvent avoir un **rang**. Le correctif de présentation prépare des états explicites : `OUI`, `NON`, `NON_PARTANT` et `NON_CALCULE`. Les sélections numériques historiques restent conservées ; aucun nouveau classement rétroactif n'est publié.

Les fichiers PMU contiennent déjà 134 rangs positifs sur les 183 déclarations du 12 novembre. Le bridge n'en transférait que 50 parce qu'il dépendait pour cela des exports Geny. Le correctif transfère les 134 rangs présents à tous les partants correspondants. Les autres cellules ne sont pas remplies avec des rangs fictifs : NP, disqualification ou absence de rang positif exigent un statut distinct.

## Limite de capacité et prochaine étape utile

Le processus partage six nouvelles consultations entre le jour J et J+1. Son créneau actif de 08 h à 20 h Paris représente théoriquement treize cycles horaires, soit au plus **78 tentatives par jour** si tous les cycles ont lieu. Les délais, erreurs et refus réduisent encore ce total. Les 290 participations sans historique ne sont pas forcément 290 nouvelles fiches distinctes ; leur volume montre toutefois qu'une couverture exhaustive immédiate n'est pas réaliste avec ce budget.

Ordre recommandé :

1. Intégrer le correctif du quota réel et le transfert des données déjà disponibles.
2. Ajouter une file des chevaux manquants dédoublonnée par identifiant stable, avec priorité aux courses proches du départ et à celles dont peu de fiches manquent pour devenir exploitables.
3. Contrôler les URL et la fraîcheur des historiques ; distinguer 404, 403/429, erreur de lecture et manque de données.
4. Faire ensuite un essai réel borné sur quelques fiches autorisées et mesurer tentatives, réussites, performances récupérées et durée. Le taux de réussite de l'accès doit être mesuré avant d'élargir.
5. Évaluer une autre source historique uniquement après validation sur les mêmes chevaux et avec des performances datées. La musique seule ne remplace pas un historique détaillé.

## Livraison et reproduction

Le correctif V24 du parseur est déjà dans `main`. Les corrections supplémentaires de quota et de présentation décrites ici sont sur la branche `test/simulation-collecte-couverture`, en attente d'intégration. Le Google Sheets et la branche de données de production n'ont pas été modifiés pendant cette simulation.

```sh
python scripts/simuler_collecte.py --cache reference_pmu --sortie resultats/simulation_v25
python -m unittest discover -s tests -p 'test_*offline.py' -q
```

Le programme exige l'historique Git contenant les versions de référence. Il bloque les accès réseau dans les scénarios synthétiques et vérifie par empreintes SHA-256 que les fichiers de référence restent inchangés. Sorties : `simulation.json`, `donnees_manquantes.csv`, `execution.log` ; le contrôle réel isolé est consigné séparément dans `controle_acces_geny.json`.

Validation : **127 tests hors ligne réussis**, dont quatre nouveaux contrôles du budget et de la couverture sans manifeste. Aucun gain de collecte réelle n'est revendiqué à partir des réponses simulées.
