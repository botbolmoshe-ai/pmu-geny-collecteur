"""Exécuter le programme PMU sous le verrou de production."""
from datetime import datetime, timedelta, timezone

from .auto_v18 import run
from .echeances_production import PARIS, lire, planifier, sauver
from .rapprochement_reunions import rapprocher


def executer(cache, plan_path, clock=lambda: datetime.now(timezone.utc)):
    plan = lire(plan_path)
    now = clock()
    mode = plan['mode']
    def preparer():
        diagnostic = run(cache, plan['date_preparation'], [], 0, now=clock(),
                         clock=clock, preparation_seule=True)
        if diagnostic['statut'] == 'ERREUR_COLLECTE' or diagnostic['partants_a_reprendre']:
            raise RuntimeError('PREPARATION_PMU_A_REPRENDRE')

    if mode == 'RAPPROCHEMENT':
        rapprocher(cache, plan, clock)
        if not plan.get('global_du'):
            if plan.get('date_preparation'):
                preparer()
            return
        # Une échéance datant de la préparation du plan reste due lorsque le
        # rapprochement est publié dans le même cycle que le global.
        plan['mode'] = mode = 'GLOBAL'
        sauver(plan_path, plan)
    if mode == 'PREPARATION_JOUR':
        return preparer()

    def actualiser():
        fresh = planifier(cache, clock())
        if fresh['mode'] != 'JALONS':
            return []
        obligations = {r['reunion']: r for r in plan['rapprochements_dus']}
        obligations.update({r['reunion']: r for r in fresh['rapprochements_dus']})
        sauver(plan_path, {**fresh, 'plan_utc': plan['plan_utc'],
                           'rapprochements_dus': list(obligations.values())})
        return fresh['selection']

    today = now.astimezone(PARIS).date()
    run(cache, today.isoformat(), plan['selection'], 0,
        max_discoveries=0, now=now, selection_complete=True, clock=clock,
        priorites=plan['selection'], production=True, prioritaire=mode == 'JALONS',
        actualiser_plan=actualiser if mode == 'GLOBAL' else None)
    if lire(plan_path)['mode'] == 'GLOBAL':
        tomorrow = today + timedelta(days=1)
        run(cache, tomorrow.isoformat(), [], 0, max_discoveries=0, now=clock(),
            selection_complete=True, clock=clock, production=True)
