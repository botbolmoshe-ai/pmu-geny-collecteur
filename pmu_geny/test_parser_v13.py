"""Tests sans navigation réseau : python -m pmu_geny.test_parser_v13"""
from .collecte_geny_v4 import lire_classement, parse_career


def essai():
    assert lire_classement(['138', "12e"]) == '12'
    assert lire_classement(['17.1', '6e']) == '6'
    assert lire_classement(['17.1', '6', 'e']) == '6'
    assert lire_classement(['4.6', 'Dai']) == 'Dai'
    assert lire_classement(['13 500 €', '4.6']) == ''
    body = ('CARRIÈRE\nsur 2 courses\nToutes\nDate\nHippodrome\n'
            '10/11/26\nVincennes\n17/10/26\nLa Capelle\n'
            '15/05\n2026\nGrosbois\nQualification\n')
    rows = [
        "10/11/26 | Vincennes | Attelé | 2850 | PP | G | - | Dur | Crse D | 33 000 € | J. Vanmeerbeck | 1'24''5 | 138 | 12e",
        "17/10/26 | La Capelle | Attelé | 2000 | G | - | Dur | Crse F | 12 500 € | J. Vanmeerbeck | 1'19''7 | 17.1 | 6e",
        "15/05/26 | Grosbois | Attelé | 2000 | Qualification | 1'20''6",
    ]
    res = parse_career(body, rows)
    assert res['nombre_annonce_geny'] == 2, res
    assert res['nombre_extrait'] == 2, res
    assert [x['classement'] for x in res['performances']] == ['12', '6'], res
    assert res['complet'] is True, res
    assert res['blocs_qualification_exclus'] == 1, res
    print('TEST V13 OK: 2 courses, rangs 12e et 6e, qualification exclue, statut COMPLET.')

if __name__ == '__main__':
    essai()
