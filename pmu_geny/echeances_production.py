"""Planifier et attester les publications H-2/H-1, sans dépendance réseau."""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
from collections import defaultdict
import os
from pathlib import Path
from dashboard.trot_analytics.dates import PARIS, instant_iso as instant

PHASES = {'H2': timedelta(hours=2), 'H1': timedelta(hours=1)}
MARGE = timedelta(minutes=30)  # fraîcheur des données, inchangée
ANTICIPATION = timedelta(minutes=55)  # fenêtres H2/H1 non superposées


def lire(path):
    try:
        return json.loads(Path(path).read_text(encoding='utf-8'))
    except FileNotFoundError:
        return {}


def sauver(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    tmp.replace(path)


def courses_du_jour(cache, now):
    day = now.astimezone(PARIS).date().isoformat()
    return day, lire(Path(cache)/'sources_pmu'/f'programme_{day}.json').get('programme', [])


def planifier(cache, now, force=False):
    if now.tzinfo is None:
        raise ValueError('Heure avec fuseau obligatoire')
    cache = Path(cache)
    previous = lire(cache/'orchestration/production_etat.json')
    last = instant(previous.get('dernier_global_publie_utc'))
    day, courses = courses_du_jour(cache, now)
    global_due = force or not last or not timedelta(0) <= now-last < timedelta(hours=1)
    selection = []
    needs = []
    upcoming = []
    for c in courses:
        depart = instant(c.get('depart'))
        if not depart or depart <= now:
            continue
        key = day+'_'+c['code']
        phases = lire(cache/'jalons'/f'{key}.json')
        for phase, offset in PHASES.items():
            deadline = depart-offset
            start = deadline-ANTICIPATION
            record = phases.get(phase, {})
            if record.get('statut') in ('PUBLIE_A_TEMPS', 'PUBLIE_EN_RETARD'):
                continue
            if now >= start:
                selection.append(c['code'])
                needs.append({'course':key, 'phase':phase, 'echeance':deadline.isoformat()})
            else:
                upcoming.append(start)
    if last and last+timedelta(hours=1)>now:
        upcoming.append(last+timedelta(hours=1))
    needs.sort(key=lambda item: (instant(item['echeance']) < now, instant(item['echeance']), item['course']))
    prioritized = list(dict.fromkeys(item['course'].split('_', 1)[1] for item in needs))
    return {'plan_utc':now.isoformat(), 'date':day,
            'executer':bool(global_due or selection),
            'mode':'GLOBAL' if global_due else 'JALONS' if selection else 'ATTENTE',
            'selection':prioritized, 'jalons_dus':needs,
            'prochain_besoin_utc':min(upcoming).isoformat() if upcoming else None}


def besoin_pmu(cache, now):
    """Réserver le créneau avant une échéance, même si le cron est retardé."""
    return 'ECHEANCE_PMU_PRIORITAIRE' if planifier(cache, now)['executer'] else None


def motif_pause_collecte_nocturne(cache, now):
    # Laisser finir un sous-processus (240 s) et sa sauvegarde avant 05 h.
    marge = timedelta(minutes=7)
    heure = now.astimezone(PARIS)
    fin = heure.replace(hour=5, minute=0, second=0, microsecond=0)
    if heure.hour >= 5 or now + marge >= fin:
        return 'HORS_CRENEAU_NOCTURNE'
    plan = planifier(cache, now)
    prochain_besoin = instant(plan['prochain_besoin_utc'])
    if plan['executer'] or (prochain_besoin and prochain_besoin <= now + marge):
        return 'ECHEANCE_PMU_PRIORITAIRE'
    return None


def plan_collecte(cache, now, *, nocturne=False):
    """Contrôle léger avant installation du navigateur et des dépendances."""
    cache=Path(cache)
    result = {'plan_utc': now.isoformat(), 'executer': True,
              'mode': 'HISTORIQUES_NOCTURNES' if nocturne else 'HISTORIQUES'}
    motif = (motif_pause_collecte_nocturne(cache, now) if nocturne else besoin_pmu(cache, now))
    if motif:
        return {**result,'executer':False,'motif':motif}
    prod=lire(cache/'collecte_incrementale/etat.json')
    back=lire(cache/'rattrapage_historiques/etat.json')
    journal=lire(cache/'etat_persistant.json')
    blocked=instant((journal.get('dernier_blocage_geny') or {}).get('utc'))
    pauses=[instant(s.get('prochain_acces_geny_utc')) for s in (prod,back)]
    if blocked:pauses.append(blocked+timedelta(minutes=30))
    pending=any(h.get('sync')=='A_FAIRE' for h in prod.get('chevaux',{}).values())
    pauses=[p for p in pauses if p and p>now]
    if pauses and not pending:
        return {**result,'executer':False,'motif':'COOLDOWN_GENY_GLOBAL',
                'prochain_acces_geny_utc':max(pauses).isoformat()}
    return result


def prevision_valide(doc, depart, now, ml=False, key=None):
    created = instant(doc.get('calcul_utc'))
    try:
        numbers = [int(h['numero']) for h in doc.get('top3', [])]
    except (KeyError, ValueError, TypeError):
        return False
    if (not created or not created <= now < depart or len(numbers) != 3 or len(set(numbers)) != 3
            or any(not 1<=n<=30 for n in numbers)):
        return False
    if instant(doc.get('depart')) != depart:
        return False
    if key and doc.get('date','')+'_'+doc.get('course','') != key:
        return False
    if ml and doc.get('statut') not in ('ML_EXPERIMENTAL_ENTRAINE_NON_CALIBRE','ML_ENTRAINE_NON_CALIBRE'):
        return False
    if ml and doc.get('experimental'):
        trained = instant(doc.get('entrainement_utc'))
        labelled = instant(doc.get('dernier_label_entrainement_utc'))
        if not trained or not labelled or not labelled <= trained <= created:
            return False
    return True


def preuves_sheets(rows, now):
    """Reconstituer les sélections effectivement lisibles dans le registre."""
    from dashboard.trot_analytics.dates import meme_date_sheets

    groups = defaultdict(list)
    for row in rows:
        day, code = row.get('date_course'), row.get('rncn')
        if day and code:
            groups[f'{day}_{code}'].append(row)
    proofs = {}
    for key, group in groups.items():
        for kind, rank, selected, version in (
            ('direct', 'top3_direct_rang', 'top3_direct_top3', 'top3_direct_utc'),
            ('ml', 'ml_rang', 'ml_top3', 'version_ml_utc'),
        ):
            picked = [row for row in group if row.get(selected) == 'OUI']
            if len(picked) != 3 or any(r.get('non_partant') != 'PARTANT' for r in picked):
                continue
            try:
                ranking = sorted((int(r[rank]), int(r['numero'])) for r in picked)
            except (KeyError, TypeError, ValueError):
                continue
            first_version = picked[0].get(version)
            if ([i for i, _ in ranking] == [1, 2, 3] and instant(first_version)
                    and all(meme_date_sheets(version, r.get(version), first_version) for r in picked[1:])):
                proofs.setdefault(key, {})[kind] = {'numeros': [n for _, n in ranking],
                                                     'calcul_utc': first_version}
    return {'lecture_utc': now.isoformat(), 'courses': proofs}


def enregistrer_publication(cache, now, plan, publie, *, sheets=None):
    """Appeler après Sheets : une tentative ou un calcul seul ne vaut pas publication."""
    from dashboard.trot_analytics.dates import meme_date_sheets
    cache = Path(cache)
    report = {'controle_utc':now.isoformat(), 'publication_reussie':bool(publie),
              'plan':plan, 'courses':[], 'erreurs':[]}
    if publie and plan.get('mode') != 'MANUEL':
        day, courses = courses_du_jour(cache, now)
        for c in courses:
            if plan.get('mode')=='JALONS' and c['code'] not in plan.get('selection',[c['code']]):
                continue
            depart = instant(c.get('depart'))
            if not depart or depart <= now:
                continue  # Aucune attestation de publication pré-départ rétrospective.
            key = day+'_'+c['code']
            profile = lire(cache/'partants_actuels'/f'{key}.json')
            captured = instant(profile.get('capture_utc'))
            try:
                eligible = {int(n) for n,h in profile.get('chevaux',{}).items() if h.get('statut_np')=='PARTANT'}
            except (ValueError,TypeError,AttributeError):
                report['erreurs'].append({'course':key,'motif':'PARTANTS_SCHEMA_INVALIDE'})
                continue
            proofs = {}
            docs = {}
            for kind, suffix in (('direct','direct'), ('ml','ml_latest')):
                path = cache/'pronostics'/f'{key}_{suffix}.json'
                doc = lire(path)
                valid = prevision_valide(doc, depart, now, ml=kind=='ml', key=key)
                if (not valid or not captured or not timedelta(0)<=now-captured<=MARGE
                        or not {int(h['numero']) for h in doc.get('top3',[])}.issubset(eligible)):
                    report['erreurs'].append({'course':key, 'mode':kind, 'motif':'TOP3_ABSENT_OU_INVALIDE'})
                    continue
                observation = instant(sheets.get('lecture_utc')) if sheets is not None else now
                if sheets is not None:
                    observed = sheets.get('courses', {}).get(key, {}).get(kind, {})
                    numbers = [int(h['numero']) for h in doc['top3']]
                    if (observed.get('numeros') != numbers or not meme_date_sheets('calcul_utc', observed.get('calcul_utc'), doc['calcul_utc'])
                            or not observation or not instant(doc['calcul_utc']) <= observation <= now or observation >= depart):
                        report['erreurs'].append({'course': key, 'mode': kind, 'motif': 'TOP3_NON_CONFIRME_SHEETS'})
                        continue
                docs[kind] = doc
                proofs[kind] = {'calcul_utc':doc['calcul_utc'], 'publication_utc':now.isoformat(),
                    'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
                    'fichier':str(path.relative_to(cache)), 'empreinte_modele':doc.get('empreinte_modele')}
                if sheets is not None:
                    proofs[kind]['lecture_sheets_utc'] = observation.isoformat()
            if 'direct' in proofs:
                from .maturite_ml import certify_shadow
                certify_shadow(cache, key, proofs['direct'], now)
                if sheets is not None:
                    sauver(cache/'publications'/'direct'/f'{key}.json',
                           {'course': key, 'depart': depart.isoformat(), 'versions': {'direct': proofs['direct']}})
            if len(proofs) == 2:
                sauver(cache/'publications'/f'{key}.json',
                       {'course':key,'depart':depart.isoformat(),'versions':proofs})
            phases = lire(cache/'jalons'/f'{key}.json')
            for phase, offset in PHASES.items():
                if phases.get(phase, {}).get('statut') in ('PUBLIE_A_TEMPS','PUBLIE_EN_RETARD'):
                    continue
                deadline = depart-offset
                if now < deadline-ANTICIPATION:
                    continue
                selected = {}
                for kind, proof in proofs.items():
                    if instant(proof['calcul_utc']) < deadline-ANTICIPATION:
                        continue
                    stamp = instant(proof['calcul_utc']).astimezone(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
                    frozen = cache/'jalons'/key/f'{phase}_{kind}_{stamp}.json'
                    if not frozen.exists():
                        sauver(frozen, docs[kind])
                    frozen_doc = lire(frozen)
                    # Une copie présente reste immuable ; ne pas l'attribuer à un autre calcul.
                    if frozen_doc != docs[kind]:
                        continue
                    selected[kind] = {**proof, 'fichier':str(frozen.relative_to(cache)),
                                      'sha256':hashlib.sha256(frozen.read_bytes()).hexdigest()}
                complete = len(selected) == 2
                phases[phase] = {'echeance':deadline.isoformat(), 'controle_utc':now.isoformat(),
                    'statut':('PUBLIE_A_TEMPS' if now<=deadline else 'PUBLIE_EN_RETARD') if complete else 'INCOMPLET',
                    'retard_secondes':max(0, (now-deadline).total_seconds()), 'versions':selected}
                if not complete:
                    report['erreurs'].append({'course':key,'phase':phase,'motif':'JALON_INCOMPLET'})
                elif now>deadline:
                    report['erreurs'].append({'course':key,'phase':phase,'motif':'JALON_PUBLIE_EN_RETARD'})
            if phases:
                sauver(cache/'jalons'/f'{key}.json', phases)
            report['courses'].append({'course':key, 'top3_direct_et_ml':len(proofs)==2, 'jalons':phases})
        if plan.get('mode') == 'GLOBAL':
            # Un retard attesté est une anomalie, pas un échec de publication globale.
            # Ne pas redéclencher indéfiniment le global au détriment des historiques.
            # Le cache ancien d'un programme ne suffit pas à valider un cycle global.
            days = [now.astimezone(PARIS).date()+timedelta(days=n) for n in (0,1)]
            stamps = [instant(lire(cache/'sources_pmu'/f'programme_{d}.json').get('date_controle_utc')) for d in days]
            if all(s and timedelta(0)<=now-s<=MARGE for s in stamps):
                sauver(cache/'orchestration/production_etat.json',
                       {'dernier_global_publie_utc':now.isoformat()})
    sauver(cache/'qualite/dernier_controle_production.json', report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cache', default='cache_pmu')
    parser.add_argument('--plan', default='resultats/plan_production.json')
    parser.add_argument('--certifier', action='store_true')
    parser.add_argument('--strict', action='store_true')
    parser.add_argument('--collecte', action='store_true')
    parser.add_argument('--collecte-nocturne', action='store_true')
    parser.add_argument('--preuve-sheets')
    args = parser.parse_args()
    now = datetime.now(timezone.utc)
    if args.certifier:
        result = enregistrer_publication(args.cache, now, lire(args.plan), os.getenv('PUBLICATION_REUSSIE')=='true',
                                            sheets=lire(args.preuve_sheets) if args.preuve_sheets else None)
    else:
        collecte = args.collecte or args.collecte_nocturne
        if collecte:
            result = plan_collecte(args.cache, now, nocturne=args.collecte_nocturne)
        else:
            result = planifier(args.cache, now, force=os.getenv('FORCER_AUTO')=='true')
        if not collecte and os.getenv('MODE_PRODUCTION','auto') != 'auto':
            result.update(executer=True, mode='MANUEL')
        sauver(args.plan, result)
        if os.getenv('GITHUB_OUTPUT'):
            with open(os.environ['GITHUB_OUTPUT'],'a') as f:
                f.write('executer='+str(result['executer']).lower()+'\n')
    print(json.dumps(result, ensure_ascii=False))
    if args.certifier and args.strict and (not result['publication_reussie'] or result['erreurs']):
        raise SystemExit(2)


if __name__ == '__main__':
    main()
