"""Priorité stricte aux partants encore à courir, puis seulement au stock."""
from datetime import timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
from . import historiques_incrementaux as inc
from .liaison_chevaux_v22 import nom_normalise


def evaluer(cache, now, state=None):
    cache=Path(cache);state=state or inc.lire(cache/inc.QUEUE,{'chevaux':{}})
    today=now.astimezone(ZoneInfo('Europe/Paris')).date()
    journal=inc.lire(cache/'etat_persistant.json',{'chevaux':{}})['chevaux']
    ids={}
    for ident,h in journal.items():ids.setdefault(nom_normalise(h.get('nom')),set()).add(str(ident))
    engagements=[];issues=[]
    for day in (today,today+timedelta(days=1)):
        program=inc.lire(cache/'sources_pmu'/f'programme_{day}.json')
        stamp=inc.instant(program.get('date_controle_utc'))
        if not stamp or not timedelta(0)<=now-stamp<=timedelta(hours=6):
            issues.append({'course':str(day),'motif':'PROGRAMME_ABSENT_OU_ANCIEN'})
            continue
        for c in program.get('programme',[]):
            depart=inc.instant(c.get('depart'))
            if not depart or depart<=now:continue
            code=str(day)+'_'+c['code'];profile=inc.lire(cache/'partants_actuels'/f'{code}.json')
            horses=profile.get('chevaux',{})
            if not horses:
                issues.append({'course':code,'motif':'PARTANTS_ABSENTS'});continue
            captured=inc.instant(profile.get('capture_utc'))
            if not captured or not timedelta(0)<=now-captured<=timedelta(hours=6):
                issues.append({'course':code,'motif':'PROFIL_PMU_ABSENT_OU_ANCIEN'})
            if c.get('nombre_declares') and len(horses)!=int(c['nombre_declares']):
                issues.append({'course':code,'motif':'LISTE_PARTANTS_INCOMPLETE'})
            pmu_ok=bool(captured and timedelta(0)<=now-captured<=timedelta(hours=6)
                        and (not c.get('nombre_declares') or len(horses)==int(c['nombre_declares'])))
            created=None
            if day==today:
                prediction=inc.lire(cache/'pronostics'/f'{code}_direct.json')
                created=inc.instant(prediction.get('calcul_utc'))
                if not created or not created<depart or len(prediction.get('top3',[]))!=3:
                    issues.append({'course':code,'motif':'PREVISION_PRELIMINAIRE_ABSENTE'})
                    # L'absence de TOP3 reste un blocage du rattrapage de fond,
                    # mais ne doit pas empêcher d'enrichir les données qui
                    # permettront précisément de calculer ce TOP3.
            for number,h in horses.items():
                if h.get('statut_np')=='NON_PARTANT':continue
                name=nom_normalise(h.get('nom'));known=ids.get(name,set())
                context=code+'_'+str(number)
                ident=next(iter(known)) if len(known)==1 else ''
                key=ident if ident in state['chevaux'] else context
                if key not in state['chevaux']:
                    matches=[k for k,v in state['chevaux'].items() if v.get('engagement')==code
                             and str(v.get('numero'))==str(number) and nom_normalise(v.get('nom'))==name]
                    key=matches[0] if len(matches)==1 else None
                linked=state['chevaux'].get(key,{})
                if not ident:ident=linked.get('id','')
                doc=inc.capture_valide(cache,ident) if ident else None
                if linked.get('sync')=='A_FAIRE':issues.append({'course':code,'motif':'PUBLICATION_HISTORIQUE_EN_ATTENTE'})
                if day==today and doc and created and inc.instant(doc.get('extrait_utc')) and inc.instant(doc['extrait_utc'])>created:
                    issues.append({'course':code,'motif':'PREVISION_A_ACTUALISER_APRES_HISTORIQUE'})
                from .ferrures_geny import manquantes
                reason=inc.actualisation_requise({**linked,
                    'historique_complet_au_utc':doc.get('extrait_utc') if doc else None,
                    'verification_periodique':True,'ferrures_manquantes':manquantes(doc) if doc else 0},now)
                horse_ok=not any(h.get(f) is None or str(h.get(f))=='' for f in ('nom','age_ans','sexe','gains_euros','ferrure'))
                if not horse_ok:
                    issues.append({'course':code,'numero':str(number),'motif':'PROFIL_PMU_INCOMPLET'})
                if reason:issues.append({'course':code,'numero':str(number),'motif':reason})
                cid=inc.course_geny_connue(cache,code)
                engagements.append({'cle_file':key,'engagement':code,'numero':str(number),'nom':h.get('nom'),
                    'preparation_pmu_ok':pmu_ok and horse_ok,
                    'depart_utc':depart.isoformat(),'motif_actualisation':reason,
                    'historique_complet':bool(doc),
                    'course_url':'https://www.geny.com/course/'+cid[5:]+'/partants-pronostics' if cid else ''})
    by_day={}
    for row in engagements:
        stats=by_day.setdefault(row['engagement'][:10],{'partants':0,'historiques_complets':0,
            'sans_historique_complet':0,'historiques_a_actualiser':0})
        stats['partants']+=1
        stats['historiques_complets']+=int(row['historique_complet'])
        stats['sans_historique_complet']+=int(not row['historique_complet'])
        stats['historiques_a_actualiser']+=int(bool(row['motif_actualisation']))
    return {'controle_utc':now.isoformat(),'pret':not issues,'partants_a_venir':len(engagements),
            'couverture_par_jour':by_day,'blocages':issues,'engagements':engagements}


def appliquer(cache,state,now):
    report=evaluer(cache,now,state)
    for h in state['chevaux'].values():h['depart_a_venir_utc']=None
    for row in sorted(report['engagements'],key=lambda r:r['depart_utc']):
        h=state['chevaux'].get(row['cle_file'])
        if h is None or h.get('depart_a_venir_utc'):continue
        h.update(depart_a_venir_utc=row['depart_utc'],engagement=row['engagement'],numero=row['numero'],
                 preparation_pmu_ok=row['preparation_pmu_ok'],
                 motif_actualisation=row['motif_actualisation'])
        if row['course_url']:h['course_url']=row['course_url']
    state['politique_collecte']='PROCHAINS_DEPARTS_SEULEMENT'
    state['preparation_prochaines_courses']={k:v for k,v in report.items() if k!='engagements'}
    return state


def autoriser_fond(cache,now):
    report=evaluer(cache,now)
    return None if report['pret'] else 'PREPARATION_PROCHAINES_COURSES_INCOMPLETE'
