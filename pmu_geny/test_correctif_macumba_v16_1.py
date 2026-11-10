"""Test local sans reseau pour le classement Di et la reutilisation du cache."""
from __future__ import annotations
import json
import tempfile
from pathlib import Path
from .collecte_geny_v4 import lire_classement
from .controle_historique import classifier
from .traitement_course import _revalider_historique_cache


def main():
    assert lire_classement(['36.2', 'Di']) == 'Di'
    assert lire_classement(['36.2', 'Dai']) == 'Dai'
    assert lire_classement(['10.8', '2', 'e']) == '2'
    assert lire_classement(['36.2']) == ''
    # Cas exact de la course du 25 septembre, sans inventer un chrono.
    doc = {"nombre_annonce_geny": 1, "nombre_extrait": 1, "dates_uniques": True,
           "statut": "DONNEES_INCOMPLETES", "performances": [{
               "date": "2026-09-25", "hippodrome": "Vincennes",
               "discipline": "Attelé", "distance_m": "2850", "classement": "", "chrono": "",
               "texte_source": "25/09/26 | Vincennes | Attelé | 2 850 | GP | G | - | Dur | Crse D | 40 000 € | P. P. Ploquin | 36.2 | Di"
           }]}
    with tempfile.TemporaryDirectory() as tmp:
        f = Path(tmp) / 'historique_geny.json'
        f.write_text(json.dumps(doc, ensure_ascii=False), encoding='utf-8')
        resultat = _revalider_historique_cache(f)
        assert resultat['statut'] == 'COMPLET', resultat
        relu = json.loads(f.read_text(encoding='utf-8'))
        assert relu['performances'][0]['classement'] == 'Di'
        assert relu['performances'][0]['chrono'] == ''
        assert classifier(relu)[0] == 'COMPLET'
    print('V16.1 OK : Di reconnu, cache revalide sans nouvelle requete Geny')


if __name__ == '__main__':
    main()
