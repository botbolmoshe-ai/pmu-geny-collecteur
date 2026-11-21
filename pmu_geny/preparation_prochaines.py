"""Priorité aux partants disponibles ; le stock utilise les créneaux libres."""
from datetime import timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
from . import historiques_incrementaux as inc
from .echeances_production import reunions_du_jour
from .liaison_chevaux_v22 import nom_normalise


def evaluer(cache, now, state=None, *, nocturne=False):
    cache=Path(cache);state=state or inc.lire(cache/inc.QUEUE,{'chevaux':{}})
    local = now.astimezone(ZoneInfo('Europe/Paris'))
    today = local.date()
    journal=inc.lire(cache/'etat_persistant.json',{'chevaux':{}})['chevaux']
    ids={}
    for ident,h in journal.items():ids.setdefault(nom_normalise(h.get('nom')),set()).add(str(ident))
    engagements=[];issues=[]
    demain = today + timedelta(days=1)
    days = (today,) if nocturne and local.hour < 21 else (today, demain)
    for day in days:
        program=inc.lire(cache/'sources_pmu'/f'programme_{day}.json')
        stamp=inc.instant(program.get('date_controle_utc'))
        if not stamp or not timedelta(0)<=now-stamp<=timedelta(hours=6):
            if not nocturne or day == today:
                issues.append({'course':str(day),'motif':'PROGRAMME_ABSENT_OU_ANCIEN'})
            continue
        premiers_departs = {course['code']: reunion['premier_depart']
                            for reunion in reunions_du_jour(cache, str(day)) if reunion['coherente']
                            for course in reunion['attendues']}
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
            if day == today and not nocturne:
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
                    'preparation_pmu_ok':pmu_ok and bool(name),
                    'depart_utc': depart.isoformat(), 'premier_depart_utc': premiers_departs.get(c['code'], depart).isoformat(),
                    'motif_actualisation':reason,
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


def appliquer(cache,state,now,*,nocturne=False):
    report=evaluer(cache,now,state,nocturne=nocturne)
    for h in state['chevaux'].values():h['depart_a_venir_utc']=None
    for row in sorted(report['engagements'], key=lambda r: (r['premier_depart_utc'], r['depart_utc'])):
        h=state['chevaux'].get(row['cle_file'])
        if h is None or h.get('depart_a_venir_utc'):continue
        h.update(depart_a_venir_utc=row['depart_utc'], premier_depart_reunion_utc=row['premier_depart_utc'],
                 engagement=row['engagement'],numero=row['numero'],
                 preparation_pmu_ok=row['preparation_pmu_ok'],
                 motif_actualisation=row['motif_actualisation'])
        if row['course_url']:h['course_url']=row['course_url']
    state['politique_collecte']='PROCHAINS_DEPARTS_SEULEMENT'
    state['preparation_prochaines_courses']={k:v for k,v in report.items() if k!='engagements'}
    return state


def decision_fond(cache,now,*,reserve=False,nocturne=False):
    """Observer la même file que le worker, sans écrire ni lever un délai de réessai."""
    cache=Path(cache)
    state=inc.alimenter(cache,now,sauvegarder=False)
    state['passage_utc']=now.isoformat()
    appliquer(cache,state,now,nocturne=nocturne)
    report=state['preparation_prochaines_courses']
    result={'controle_utc':now.isoformat(),'autorise':False,'motif':None,
            'preparation_complete':report['pret'],
            'couverture_par_jour':report['couverture_par_jour']}
    def refuser(reason):
        result['motif']=reason
        return result
    journal=inc.lire(cache/'etat_persistant.json')
    blocked=inc.instant((journal.get('dernier_blocage_geny') or {}).get('utc'))
    back=inc.lire(cache/'rattrapage_historiques/etat.json')
    pauses=[inc.instant(s.get('prochain_acces_geny_utc')) for s in (state,back)]
    if blocked:pauses.append(blocked+timedelta(minutes=30))
    pauses=[p for p in pauses if p and p>now]
    if pauses:
        result['prochain_acces_geny_utc']=max(pauses).isoformat()
        return refuser('COOLDOWN_GENY_GLOBAL')
    # Les contrôles PMU restent obligatoires. La nuit, le TOP3 n'est pas attendu.
    historical={'HISTORIQUE_ABSENT_OU_NON_DATE','PUBLICATION_GENY_EN_ATTENTE',
                'NOUVELLE_COURSE_OFFICIELLE','FERRURES_HISTORIQUES_A_COMPLETER',
                'VERIFICATION_PERIODIQUE'}
    issues=[b for b in report['blocages'] if b['motif'] not in historical]
    if issues:
        result['blocages']=issues
        return refuser('PREPARATION_PROCHAINES_COURSES_INCOMPLETE')
    if any(h.get('sync')=='A_FAIRE' for h in state['chevaux'].values()):
        return refuser('PUBLICATION_HISTORIQUE_EN_ATTENTE')
    key,action=inc.prochaine_tache(state,now,{})
    if key is not None:
        result['tache_prioritaire']={'cle':key,'action':action}
        from .echeances_production import planifier
        marker = inc.instant(back.get('dernier_creneau_reserve_utc'))
        prioritaire = state['chevaux'][key]
        depart = inc.instant(prioritaire.get('depart_a_venir_utc'))
        plan = planifier(cache, now) if reserve else {}
        next_pmu = inc.instant(plan.get('prochain_besoin_utc'))
        if (reserve and action == 'COLLECTE' and depart and depart - now > timedelta(minutes=30)
                and not plan.get('executer') and next_pmu and next_pmu - now >= timedelta(minutes=10)
                and (not marker or now - marker >= timedelta(hours=6))):
            result.update(autorise=True, motif='CRENEAU_RATTRAPAGE_BORNE', creneau_reserve=True)
            return result
        return refuser('PARTANT_PRIORITAIRE_DISPONIBLE')
    # Un cheval peut redevenir disponible pendant un sous-processus de 240 s.
    # Garder cinq minutes pour sa reprise, les sauvegardes et la pause de cadence.
    retries=[]
    for h in state['chevaux'].values():
        depart=inc.instant(h.get('depart_a_venir_utc'))
        retry=inc.instant(h.get('prochain_essai_utc'))
        if (depart and depart>now and h.get('preparation_pmu_ok')
                and h.get('motif_actualisation') and (h.get('geny') or h.get('course_url') or h.get('recherche_geny_par_nom'))
                and retry and now<retry<depart):retries.append(retry)
    if retries:
        result['prochaine_reprise_prioritaire_utc']=min(retries).isoformat()
        if min(retries)-now<=timedelta(minutes=5):
            return refuser('REPRISE_PARTANT_PRIORITAIRE_IMMINENTE')
    result.update(autorise=True,motif='PREPARATION_COMPLETE' if report['pret'] else 'CRENEAU_LIBRE_ENTRE_PARTANTS')
    return result


def autoriser_fond(cache,now,*,diagnostic=None,reserve=False,nocturne=False):
    report=decision_fond(cache,now,reserve=reserve,nocturne=nocturne)
    if diagnostic:
        import json
        inc.ecrire(diagnostic,report)
        print('ORDONNANCEMENT_FOND '+json.dumps(report,ensure_ascii=False),flush=True)
    return None if report['autorise'] else report['motif']
