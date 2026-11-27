"""Comparer l'état courant attendu et les données relues dans le registre."""
import argparse
from collections import Counter
import json
import os
from pathlib import Path

from dashboard.trot_analytics.correspondance_geny import CHAMP, NON_EFFECTUEE
from .moteur_sheets import SynchroniseurSheets, verrou_local
from .reconciliation_historiques import CHAMPS_HISTORIQUE, ReconciliationHistoriques
from .controle_sync_sheets import HISTORY


def auditer(engine):
    with verrou_local(engine.spreadsheet):
        tables = engine.metadata()
        history = engine._lire_historique_courant(tables[HISTORY])
        courses = engine.lire_courses(tables)
        reconciliation = ReconciliationHistoriques(engine.cache, history)
        diagnostics, ecarts = reconciliation.participations(courses, {})
        stock = reconciliation.stock()

    def repartir(rows, key, default):
        return dict(Counter(row.get(key) or default for row in rows))

    champs = CHAMPS_HISTORIQUE | {CHAMP}
    existing = {f"{row.get('course_key')}|{row.get('numero')}": row for row in courses}
    details = {key: {'nom': existing[key].get('cheval'),
                     'publie': {f: existing[key].get(f) for f in champs}, 'attendu': diagnostic}
               for key, diagnostic in diagnostics.items()}
    cases = {key: value for key, value in details.items()
             if key in ('2026-11-13|VINCENNES|R1C2|1', '2026-11-13|VINCENNES|R1C2|2',
                        '2026-11-14|MARSEILLE BORELY|R3C1|3')}
    return {
        'bilan': {'lignes_historique': len(history), 'participations_controlees': len(details),
                  'ecarts': dict(ecarts),
                  'etats_publies': repartir((row['publie'] for row in details.values()),
                                            'historique_statut', 'NON_RENSEIGNE'),
                  'etats_attendus': repartir(diagnostics.values(), 'historique_statut', 'NON_RENSEIGNE'),
                  'cibles_inventoriees': len(stock),
                  'correspondances_stock': repartir(stock.values(), CHAMP, NON_EFFECTUEE),
                  'historiques_stock': repartir(stock.values(), 'historique_statut', 'NON_QUALIFIE'),
                  'cas_ticket': cases},
        'participations': details,
        'stock': stock,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cache', type=Path, required=True)
    parser.add_argument('--sortie', type=Path, required=True)
    parser.add_argument('--appliquer', action='store_true')
    args = parser.parse_args()
    engine = SynchroniseurSheets(args.cache, os.environ['GOOGLE_SHEETS_ID'])
    try:
        before = auditer(engine)
        result = {'avant': before}
        if args.appliquer:
            engine.synchroniser_correspondances(include_kpi=True)
            result['apres'] = auditer(engine)
        args.sortie.parent.mkdir(parents=True, exist_ok=True)
        args.sortie.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        for stage, audit in result.items():
            print('AUDIT_HISTORIQUES ' + stage + ' ' + json.dumps(audit['bilan'], ensure_ascii=False))
        if args.appliquer and any(val for key, val in result['apres']['bilan']['ecarts'].items()
                                  if key != 'cle_participation_ambigue'):
            raise SystemExit('Écarts restants après relecture du registre')
    finally:
        engine.fermer()


if __name__ == '__main__':
    main()
