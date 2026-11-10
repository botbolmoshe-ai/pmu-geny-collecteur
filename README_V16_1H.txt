V16 — PARAMETRAGE COOLDOWN 1 HEURE

Installation : copier le CONTENU du dossier pmu_v16 a la racine du depot GitHub, puis Commit to main / Push origin.
Workflow : Actions > PMU - V16 Decouverte et collecte incrementale.
Mode decouvrir : genere et conserve le manifeste ; mode collecter : reutilise le manifeste sans nouvelle decouverte.
Cooldown Geny : 1 heure (3600 secondes) apres une erreur 403/429, partage entre les deux modes.
Ce delai est une regle locale de prudence, pas un engagement du site Geny de retablir l acces en 1h.
Si pmu-data contient deja un dernier blocage, le programme compare l heure courante a celle de ce blocage avec la nouvelle duree de 1h.
Les historiques existants restent conserves sur la branche pmu-data.
La connexion Google Sheets et la generation automatique TOP3 ne sont pas incluses.
