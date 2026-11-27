"""Exécuter les obligations PMU sous le verrou de production."""
from datetime import datetime, timedelta, timezone

from .auto_v18 import run
from .echeances_production import PARIS, lire, planifier, sauver


def executer(cache, plan_path, clock=lambda: datetime.now(timezone.utc)):
    plan = lire(plan_path)
    now = clock()
    mode = plan['mode']
    global_du = plan.get('global_du', mode == 'GLOBAL')

    def preparer():
        diagnostic = run(cache, plan['date_preparation'], [], 0, now=clock(),
                         clock=clock, preparation_seule=True)
        if diagnostic['statut'] == 'ERREUR_COLLECTE' or diagnostic['partants_a_reprendre']:
            raise RuntimeError('PREPARATION_PMU_A_REPRENDRE')

    if mode == 'PREPARATION_JOUR' or (mode == 'RAPPROCHEMENT' and not global_du):
        return preparer() if plan.get('date_preparation') else None

    # Les modalités de calcul et de publication globales restent actives lorsque
    # le programme actualisé révèle des jalons. Ceux-ci passent en tête du calcul.
    if global_du:
        plan['mode'] = 'GLOBAL'
        sauver(plan_path, plan)

    def actualiser():
        fresh = planifier(cache, clock())
        obligations = {r['reunion']: r for r in plan['rapprochements_dus']}
        obligations.update({r['reunion']: r for r in fresh['rapprochements_dus']})
        sauver(plan_path, {**plan, 'selection': fresh['selection'],
                           'jalons_dus': fresh['jalons_dus'], 'erreurs': fresh['erreurs'],
                           'prochain_jalon_utc': fresh['prochain_jalon_utc'],
                           'prochain_rapprochement_utc': fresh['prochain_rapprochement_utc'],
                           'prochain_besoin_utc': fresh['prochain_besoin_utc'],
                           'rapprochements_dus': list(obligations.values())})
        return fresh['selection']

    today = now.astimezone(PARIS).date()
    run(cache, today.isoformat(), [] if global_du else plan['selection'], 0,
        max_discoveries=0, now=now, selection_complete=True, clock=clock,
        priorites=plan['selection'], production=True, prioritaire=mode == 'JALONS' and not global_du,
        actualiser_plan=actualiser if global_du else None)
    if global_du:
        tomorrow = today + timedelta(days=1)
        run(cache, tomorrow.isoformat(), [], 0, max_discoveries=0, now=clock(),
            selection_complete=True, clock=clock, production=True)
