V16.1 - Correctif de donnees de Macumba du Vivier (ID 2849465)

- Accepte le classement Geny « Di » comme classement de non-arrivee distinct de « Dai ».
- Revalide les historiques partiels presents dans la branche pmu-data, sans appeler Geny.
- Met a jour le JSON et le CSV du cache lorsque le classement est identifiable.
- Ne cree aucun chrono absent.
- Conserve les 14 lignes de Macumba et leur nombre annonce.
- Preserve la separation decouverte/collecte et le cooldown de 1 heure.

INSTALLATION : copier le contenu du dossier pmu_v16 a la racine du depot,
puis Commit to main et Push origin dans GitHub Desktop.

TEST LOCAL : python -m pmu_geny.test_correctif_macumba_v16_1

TEST GITHUB : lancer l'action PMU - V16, mode collecter, course R2C8.
La revalidation du cache precede toute consultation de la fiche Macumba.
Le run peut contacter Geny pour d'autres chevaux absents du cache.
