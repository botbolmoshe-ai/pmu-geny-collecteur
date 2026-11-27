"""V18: orchestration horaire prudente sur sources PMU et Geny.

Le PMU fournit le programme et les statuts NP seulement si le schéma est reconnu.
Geny reste optionnel et soumis à sa politique de refus/cooldown. Aucune
prévision ni arrivée n'est inventée quand les données sont indisponibles.
"""
from __future__ import annotations
import argparse, json, os, re, sys, unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from zoneinfo import ZoneInfo
from .export_v17 import exporter

PARIS=ZoneInfo('Europe/Paris')
BASE='https://online.turfinfo.api.pmu.fr/rest/client/1/programme/'

def save(path, doc):
    path=Path(path); path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_suffix('.tmp');temp.write_text(json.dumps(doc,ensure_ascii=False,indent=2),encoding='utf-8');temp.replace(path)

def load(path, default=None):
    try: return json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError,ValueError): return default

def get_json(url, timeout=16):
    if not url.startswith(BASE): raise ValueError('Endpoint PMU non autorisé')
    req=Request(url,headers={'Accept':'application/json','User-Agent':'PMU-research-v18/1.0'})
    with urlopen(req,timeout=timeout) as response:
        if response.status!=200: raise RuntimeError(f'PMU_HTTP_{response.status}')
        body=response.read(5_000_001)
        if len(body)>5_000_000: raise RuntimeError('Réponse trop volumineuse')
        result=json.loads(body)
        if not isinstance(result,(dict,list)): raise ValueError('Format JSON PMU incompatible')
        return result

def _list(doc, *names):
    if isinstance(doc,list):return doc
    for name in names:
        x=doc.get(name)
        if isinstance(x,list):return x
    return []

def _num(doc,*fields):
    for field in fields:
        value=doc.get(field)
        if value is not None:
            try: return int(value)
            except (ValueError,TypeError): pass
    return None

def _str(doc,*fields):
    for field in fields:
        v=doc.get(field)
        if isinstance(v,str) and v.strip():return v.strip()
    return ''

def _country_code(reunion):
    """Inspecter les emplacements connus, sans déduire la France d'un nom."""
    hippodrome=reunion.get('hippodrome') or {}
    values=[]
    for obj in (reunion,hippodrome):
        if isinstance(obj,dict):
            for key in ('pays','codePays','codePaysHippodrome','paysReunion'):
                v=obj.get(key)
                if isinstance(v,dict):
                    values += [v.get(k) for k in ('code','codePays','codeIso','libelle','nom')]
                else: values.append(v)
    for v in values:
        if v is not None and str(v).strip(): return str(v).strip().upper()
    return ''


def programme_diagnostic(doc, date):
    """Retourne les courses et les compteurs exacts des exclusions PMU."""
    root=doc.get('programme',doc) if isinstance(doc,dict) else doc
    reunions=_list(root,'reunions')
    if not reunions:
        raise ValueError('Programme PMU non reconnu : clé reunions absente ou vide')
    diag={'reunions_recues':len(reunions),'reunions_francaises':0,
          'reunions_pays_inconnu':0,'reunions_etrangeres':0,
          'courses_recues':0,'courses_retenues':0,
          'exclusions':{},'pays_observes':{},'exemples_reunions':[]}
    output=[]
    inventory=[]
    courses_jalons=[]
    decision_courses=[]
    from .selection_metier_v20_4 import discipline_course, niveau
    from .resultats_v18 import podium_programme
    from .echeances_production import course_annulee
    def exclusion(reason):
        diag['exclusions'][reason]=diag['exclusions'].get(reason,0)+1
    for r in reunions:
        if not isinstance(r,dict):
            exclusion('reunion_non_dict');continue
        country=_country_code(r)
        diag['pays_observes'][country or 'INCONNU']=diag['pays_observes'].get(country or 'INCONNU',0)+1
        if len(diag['exemples_reunions'])<5:
            diag['exemples_reunions'].append({'pays':country or 'INCONNU',
                'champs_reunion':sorted(r.keys()),
                'champs_hippodrome':sorted((r.get('hippodrome') or {}).keys()) if isinstance(r.get('hippodrome'),dict) else []})
        entries=_list(r,'courses');diag['courses_recues']+=len(entries)
        if country not in ('FRA','FR','FRANCE','250'):
            if not country:diag['reunions_pays_inconnu']+=1;exclusion('pays_absent')
            else:diag['reunions_etrangeres']+=1;exclusion('pays_etranger')
            continue
        diag['reunions_francaises']+=1
        numero_reunion=_num(r,'numOfficiel','numeroReunion','numReunion')
        hip=r.get('hippodrome') or {}
        hp=_str(hip,'libelleLong','libelleCourt','nom') if isinstance(hip,dict) else str(hip)
        candidats_reunion = []
        reunion_suivie = False
        for c in entries:
            if not isinstance(c,dict):exclusion('course_non_dict');continue
            no=_num(c,'numOrdre','numeroCourse','numCourse')
            if no is None or numero_reunion is None:exclusion('numero_manquant');continue
            depart=c.get('heureDepart') or c.get('heureDepartEstimee')
            instant = (datetime.fromtimestamp(depart/1000 if depart>10**11 else depart,
                                              tz=timezone.utc).astimezone(PARIS)
                       if isinstance(depart, (int, float)) else None)
            podium_definitif = podium_programme(c)
            inventory.append({'code': f'R{numero_reunion}C{no}', 'date': date,
                              'hippodrome': hp, 'depart': instant.isoformat() if instant else None,
                              'statut_pmu': c.get('statut'), 'top3_attendu': False,
                              'podium_definitif_pmu': podium_definitif})
            if not instant:
                exclusion('heure_depart_absente');continue
            if instant.date().isoformat() != date:
                exclusion('date_incoherente');continue
            course_inventaire = inventory[-1]
            in_scope = discipline_course(c, r).startswith('TROT_')
            if in_scope:
                candidats_reunion.append(course_inventaire)
            plage = (7 <= instant.hour < 21 or
                     (instant.hour == 21 and not (instant.minute or instant.second or instant.microsecond)))
            nb = _num(c, 'nombreDeclaresPartants', 'nombrePartants', 'nbPartants')
            if not nb or not 1 <= nb <= 30:
                exclusion('partants_absents_ou_invalides')
                continue
            tier, motif, metadata = niveau(c, r, hp, nb)
            if plage:
                decision_courses.append({'code': course_inventaire['code'], 'niveau': tier or 'EXCLU',
                                         'motif': motif, **metadata})
            course = {'priorite_metier': tier, 'motif_selection': motif,
                      'allocation_eur': metadata['allocation_eur'], 'date': date,
                      'code': course_inventaire['code'], 'hippodrome': hp,
                      'nom': _str(c, 'libelle', 'nomCourse'), 'depart': instant.isoformat(),
                      'nombre_declares': nb, 'num_reunion': numero_reunion, 'num_course': no,
                      'distance_m': _num(c, 'distance', 'distanceMetres', 'distanceCourse'),
                      'discipline': metadata['discipline'], 'podium_definitif_pmu': podium_definitif,
                      'parametres_pmu': {k: c[k] for k in (
                          'distance', 'discipline', 'specialite', 'parcours', 'conditions',
                          'conditionAge', 'conditionSexe', 'categorieParticularite', 'montantPrix',
                          'typePiste', 'corde', 'typeDepart') if c.get(k) is not None}}
            if in_scope:
                course_inventaire.update(course)
            if course_annulee(course_inventaire):
                exclusion('course_annulee')
            elif not plage:
                exclusion('depart_hors_plage_07_21')
            elif tier is None:
                exclusion('metier_'+motif.lower())
            else:
                reunion_suivie = True
                output.append(course)
        if reunion_suivie:
            for course in candidats_reunion:
                course['top3_attendu'] = not course_annulee(course)
                if course.get('nombre_declares'):
                    courses_jalons.append(course)
    diag['courses_retenues']=len(output)
    diag['courses_p1']=sum(c['priorite_metier']=='P1' for c in output)
    diag['courses_p2']=sum(c['priorite_metier']=='P2' for c in output)
    diag['decisions_metier']=decision_courses
    diag['inventaire_reunions']=inventory
    diag['courses_jalons']=courses_jalons
    return sorted(output,key=lambda x:x['depart']),diag


def programme(doc,date):
    return programme_diagnostic(doc,date)[0]

def normalize(s):
    s=unicodedata.normalize('NFD',s.casefold());s=''.join(c for c in s if not unicodedata.combining(c))
    return re.sub('[^a-z0-9]+','-',s).strip('-')

def np_participants(doc, manifest):
    """Ne confirme zéro NP que si la liste complète, ses numéros et ses drapeaux sont interprétables."""
    entries=_list(doc,'participants','partants')
    if not entries: raise ValueError('Liste PMU absente')
    horses=manifest['courses'][0]['partants']
    expected={int(h['numero']) for h in horses}
    mapping={}
    for item in entries:
        if not isinstance(item,dict):raise ValueError('Participant PMU invalide')
        n=_num(item,'numPmu','num','numero','numeroPmu')
        if n in mapping or n is None: raise ValueError('Numéros PMU ambigus')
        explicit=item.get('nonPartant',None)
        if isinstance(explicit,bool): np=explicit
        elif isinstance(explicit,str) and explicit.lower() in ('true','false'):np=explicit.lower()=='true'
        elif str(item.get('statut','')).upper() in ('NP','NON_PARTANT'):np=True
        elif str(item.get('statut','')).upper() in ('PARTANT',):np=False
        else:raise ValueError('Indicateur NP absent ou inconnu sur un participant')
        mapping[n]=np
    if set(mapping)!=expected: raise ValueError(f'Liste PMU incomplète/incohérente: {len(mapping)}/{len(expected)}')
    return mapping

def update_np(cache, course, manifest, pmu_data):
    mapped=np_participants(pmu_data,manifest)
    cid=manifest['courses'][0]['course_id']; target=cache/'participations'/f'{cid}.json'
    previous=load(target,{}) or {}; old={x['numero']:x for x in previous.get('chevaux',[])}
    now=datetime.now(timezone.utc).isoformat(); rows=[]
    for p in manifest['courses'][0]['partants']:
        n=int(p['numero']); statut='NON_PARTANT' if mapped[n] else 'PARTANT'
        rows.append({'numero':n,'cheval_id':str(p['id']),'nom':p['nom'],'statut_participation':statut,
                     'source_np':'PMU_API','date_verification_np':now})
    doc={'course_id':cid,'source_reference':'PMU','source_url':f"{BASE}{course['date'].replace('-','')}",
         'date_controle_utc':now,'liste_complete_verifiee':True,'chevaux':rows,
         'historique_modifications':previous.get('historique_modifications',[])+[{'utc':now,'numero':r['numero'],'ancien':old.get(r['numero'],{}).get('statut_participation','NP_NON_VERIFIE'),
                                       'nouveau':r['statut_participation']} for r in rows if old.get(r['numero'],{}).get('statut_participation')!=r['statut_participation']]}
    save(target,doc);return doc

def run(cache:Path, date:str, selection:list[str], max_new:int, phase:str='auto', max_discoveries:int=2, now=None, selection_complete=None, clock=None, priorites=(), production=False, prioritaire=False, actualiser_plan=None, preparation_seule=False):
    if clock is None:
        clock=(lambda:now) if now is not None else (lambda:datetime.now(PARIS))
    now=now or clock()
    if now.tzinfo is None: raise ValueError("Heure de traitement sans fuseau")
    index=cache/'orchestration'/f'{date}.json'; state=load(index,{'date':date,'courses':{},'alertes':[]})
    # Les diagnostics sont persistés même en cas de source vide ou invalide.
    # Une erreur de consultation ne signifie jamais "aucune course".
    controle={'date':date,'horodatage_utc':clock().astimezone(timezone.utc).isoformat(),
              'source_url':BASE+datetime.fromisoformat(date).strftime('%d%m%Y'),
              'statut':'NON_VERIFIE','courses_retenues':0}
    try:
        pmu=get_json(controle['source_url'])
        courses,stats=programme_diagnostic(pmu,date)
        controle.update(stats)
        if not courses:
            controle['statut']='ZERO_COURSE_A_DIAGNOSTIQUER'
            state['alertes'].append('PMU_ZERO_COURSE: programme reçu, aucun candidat retenu; voir diagnostics_pmu')
        else:
            controle['statut']='COURSES_DISPONIBLES'
        save(cache/'sources_pmu'/f'programme_{date}.json',
             {'date_controle_utc':controle['horodatage_utc'],'programme':courses, 'inventaire_reunions':stats.get('inventaire_reunions', courses),
              'courses_jalons':stats.get('courses_jalons', courses)})
        state['source_programme']='PMU_API'
        state['dernier_controle_pmu']=controle['horodatage_utc']
    except Exception as exc:
        controle['statut']='ERREUR_COLLECTE'
        controle['erreur']=f'{type(exc).__name__}: {exc}'
        state['alertes'].append(f"PMU_ERREUR_COLLECTE: {controle['erreur']}")
        courses=(load(cache/'sources_pmu'/f'programme_{date}.json',{}) or {}).get('programme',[])
        controle['courses_depuis_cache']=len(courses)
    state['diagnostic_pmu']=controle
    save(cache/'sources_pmu'/f'diagnostic_{date}.json',controle)
    print('DIAGNOSTIC_PMU '+json.dumps(controle,ensure_ascii=False))
    if actualiser_plan:
        cible = actualiser_plan()
        if cible:
            selection, priorites, prioritaire = cible, cible, True
    codes_metier = {c['code'] for c in courses}
    if prioritaire or (production and date == now.astimezone(PARIS).date().isoformat()):
        # La certification du jour couvre toutes les courses attendues de la réunion.
        programme_cache = load(cache/'sources_pmu'/f'programme_{date}.json', {}) or {}
        courses = programme_cache.get('courses_jalons', courses)
    # Une course déjà partie n'entre JAMAIS en prédiction/collecte.
    # Les courses récentes peuvent seulement passer par la phase arrivées/audit.
    # Le lendemain est prepare des publication du programme PMU, sans limitation a 18h.
    from .planification_v20_2 import selectionner_courses
    selected=selectionner_courses(courses, now, date, selection, True if selection_complete is None else selection_complete,
                                state, max_courses=len(courses))
    if production:
        selected = [c for c in selected if datetime.fromisoformat(c['depart']) > now]
    order = {code: index for index, code in enumerate(priorites)}
    if order:
        selected.sort(key=lambda course: order.get(course['code'], len(order)))
    from .cotes_v19 import calculer_cotes, collecter
    from .planification_v20_2 import decision_autorisee

    participants_by_course = {}

    def charger_participants(code):
        if code not in participants_by_course:
            raw = None
            error = ''
            try:
                reunion, number = code.split('C', 1)
                raw = get_json(BASE + datetime.fromisoformat(date).strftime('%d%m%Y')
                               + f'/{reunion}/C{number}/participants')
            except Exception as exc:
                error = f'{type(exc).__name__}: {exc}'
            participants_by_course[code] = (raw, clock(), error)
        return participants_by_course[code]

    if preparation_seule:
        from .echeances_production import profil_preparation_disponible
        from .partants_actuels_v21 import enregistrer

        erreurs_partants = []
        for course in courses:
            if profil_preparation_disponible(cache, date, course, clock()):
                continue
            raw, observed, error = charger_participants(course['code'])
            if error or enregistrer(cache, course, raw, observe=observed) != 'PARTANTS_ACTUELS_ENREGISTRES':
                erreurs_partants.append(course['code'])
        controle['partants_a_reprendre'] = erreurs_partants
        save(cache/'sources_pmu'/f'diagnostic_{date}.json', controle)
        return controle

    # Enregistrer le marché avant les enrichissements et partager une requête
    # par course entre collecte, modèles, contrôle des NP et résultats.
    for course in selected:
        depart = datetime.fromisoformat(course['depart'])
        if not decision_autorisee(clock(), date, depart):
            continue
        code = course['code']
        entry = state['courses'].setdefault(code, {'identifiant_geny': None, 'etat': 'A_DECOUVRIR'})
        raw, observed, error = charger_participants(code)
        if error:
            entry['erreur_pmu_participants'] = error
        else:
            entry.pop('erreur_pmu_participants', None)
        try:
            entry['statut_cotes'] = collecter(cache, course, raw, now=observed)
            entry.pop('erreur_cotes', None)
        except Exception as exc:
            entry['erreur_cotes'] = f'{type(exc).__name__}: {exc}'
        try:
            entry['statut_top3_cotes'] = calculer_cotes(cache, course, observed, clock)
            entry.pop('erreur_top3_cotes', None)
        except Exception as exc:
            entry['erreur_top3_cotes'] = f'{type(exc).__name__}: {exc}'

    remaining_new=max_new
    remaining_discoveries=max_discoveries
    correspondences_path=cache/'orchestration'/'correspondances_geny.json'
    correspondences=load(correspondences_path,{}) or {}
    from .echeances_production import pause_geny_active
    cooldown = bool(pause_geny_active(cache, datetime.now(timezone.utc)))
    geny_index=None
    if remaining_discoveries>0 and not cooldown and any(datetime.fromisoformat(c['depart'])>now for c in selected):
        try:
            from .rapprochement_v20_6 import index_programme
            geny_index=index_programme(cache,date,cache/'etat_persistant.json')
            print(f"INDEX_GENY date={date} statut={geny_index.get('statut')} courses={len(geny_index.get('courses',[]))} codes_rc_documentes={geny_index.get('codes_rc_documentes',0)}",flush=True)
            if geny_index.get('statut')=='GENY_BLOQUE':cooldown=True
        except Exception as exc:
            state['alertes'].append(f'INDEX_GENY: {type(exc).__name__}: {exc}')
    # Rapprocher TOUTES les courses sélectionnées sur l'index journalier déjà
    # consulté. L'association n'ouvre aucune fiche Geny et ne consomme pas le
    # quota de découverte des partants. Ne pas confondre correspondance et
    # manifeste complet.
    decisions_geny = {}
    if geny_index and geny_index.get('statut') == 'OK':
        from .rapprochement_v20_6 import rapprocher
        for candidate_course in selected:
            if datetime.fromisoformat(candidate_course['depart']) <= now:
                continue
            code = candidate_course['code']
            decision = rapprocher(candidate_course, geny_index['courses'])
            decisions_geny[code] = decision
            record = state['courses'].setdefault(code, {'identifiant_geny': None, 'etat': 'A_DECOUVRIR'})
            record['rapprochement_geny'] = decision
            if decision.get('statut') == 'CORRESPONDANCE_CONFIRMEE':
                record['geny_id_rapproche'] = decision['geny_id']
            else:
                record.pop('geny_id_rapproche', None)
            print('RAPPROCHEMENT_GENY '+json.dumps({
                'date': date, 'course_pmu': code,
                'statut': decision.get('statut'),
                'methode': decision.get('methode'),
                'geny_id': decision.get('geny_id')
            }, ensure_ascii=False), flush=True)
    for c in selected:
        now=clock()
        key=c['code']; entry=state['courses'].setdefault(key,{'identifiant_geny':None,'etat':'A_DECOUVRIR'})
        entry.update({'depart':c['depart'],'nom':c['nom'],'hippodrome':c['hippodrome'],'nombre_declares':c['nombre_declares'], 'priorite_metier':c.get('priorite_metier'), 'motif_selection':c.get('motif_selection')})
        departure=datetime.fromisoformat(c['depart'])
        est_partie=now>=departure
        fenetre_decision=decision_autorisee(now,date,departure)
        # Aucune prévision rétroactive, même si PMU n'a pas encore communiqué le statut.
        if est_partie:
            entry['traitement']='RESULTATS_SEULEMENT'
            if (cache/'arrivees'/f"{date}_{key}.json").exists() and entry.get('audit_predictif') in ('AUDIT_ENREGISTRE','AUDIT_DEJA_ENREGISTRE'):
                entry['etat']='TERMINE_ARCHIVE'
                continue
        else:
            entry['traitement']='PREPARATION_AVANT_DEPART'
        # Météo sourcée indépendante de Geny et des statuts NP : même sans manifeste.
        cycle_leger = prioritaire or key not in codes_metier
        if not est_partie and not cycle_leger:
            try:
                from .contexte_meteo_v20 import collecter_meteo
                entry['statut_meteo']=collecter_meteo(cache,c)
            except Exception as exc:
                entry['statut_meteo']='METEO_NON_VERIFIEE'
                entry['erreur_meteo']=f'{type(exc).__name__}: {exc}'
        # PMU independant : produire les niveaux direct et cotes meme sans Geny.
        # Avant depart seulement. Ne jamais bloquer ces TOP3 sur les historiques.
        pmu_participants, observed, error = charger_participants(key)
        if error:
            entry['erreur_pmu_participants'] = error
        else:
            entry.pop('erreur_pmu_participants', None)
        now = clock()
        est_partie = now >= departure
        fenetre_decision = decision_autorisee(now, date, departure)
        if est_partie:
            entry['traitement'] = 'RESULTATS_SEULEMENT'
        try:
            if pmu_participants is not None:
                try:
                    from .partants_actuels_v21 import enregistrer
                    entry['statut_partants_actuels'] = enregistrer(cache, c, pmu_participants, observe=observed)
                except Exception as exc:
                    entry['erreur_partants_actuels'] = f'{type(exc).__name__}: {exc}'
            if not cycle_leger and not est_partie and pmu_participants is not None:
                try:
                    from .sources_experts_v23 import collecter as collecter_avis
                    entry['statut_avis_experts'] = collecter_avis(cache, c, pmu_participants)
                except Exception as exc:
                    entry['statut_avis_experts'] = 'EXPERTS_NON_VERIFIES'
                    entry['erreur_avis_experts'] = f'{type(exc).__name__}: {exc}'
            if fenetre_decision and pmu_participants is not None:
                try:
                    from .top3_independants_v22 import calculer
                    direct = calculer(cache, c, pmu_participants, now=observed, clock=clock, inclure_cotes=False)
                    if isinstance(direct, dict):
                        entry['paliers_independants'] = {**direct, 'cotes': entry.get('statut_top3_cotes')}
                except Exception as exc:
                    entry['erreur_paliers_independants'] = f'{type(exc).__name__}: {exc}'
                evidence = None
                # Desormais la capture ML ne depend ni de Geny ni des historiques.
                try:
                    from .ml_v19 import pmu_rows, snapshot_pmu, predict_pmu
                    evidence = pmu_rows(cache, c, pmu_participants, observed)
                    entry['statut_snapshot_ml']=snapshot_pmu(cache,c,pmu_participants,now=observed,clock=clock, prepared=evidence)
                    entry['statut_ml']=predict_pmu(cache,c,pmu_participants,now=observed,clock=clock, prepared=evidence)
                except Exception as exc:
                    entry['erreur_ml']=f'{type(exc).__name__}: {exc}'
                if entry.get('paliers_independants', {}).get('direct') in ('CALCULE_COMPLET', 'CALCULE_PARTIEL'):
                    try:
                        from .maturite_ml import score_shadow
                        score_shadow(cache,c,pmu_participants,observed,clock, prepared=evidence)
                    except Exception as exc:
                        entry['erreur_ml_preproduction']=f'{type(exc).__name__}: {exc}'
            if production and not est_partie and pmu_participants is not None:
                from .ipr import actif, enregistrer as enregistrer_ipr
                if actif():
                    try:
                        entry['statut_ipr'] = enregistrer_ipr(cache, c, pmu_participants, observed, clock)
                    except Exception as exc:
                        entry['erreur_ipr'] = type(exc).__name__
                        print(f'::warning::Calcul IPR indisponible pour {date}_{key}', flush=True)
        except Exception as exc:
            entry['erreur_paliers_independants']=f'{type(exc).__name__}: {exc}'
        if cycle_leger or (production and est_partie):
            continue
        # Pas de consultation Geny sur une course terminee.
        manifest=None; manifest_path=None
        for f in (cache/'manifestes').glob('GENY-*.json') if (cache/'manifestes').exists() else []:
            m=load(f,{})
            if not m or not m.get('courses'):continue
            block=m['courses'][0]
            match=correspondences.get(f'{date}_{key}')==block.get('course_id')
            if not match:
                # Rétrocompatibilité V16/V17: vérifier également l'hippodrome,
                # jamais le nom seul. Un rapprochement de cache erroné est durable.
                u=block.get('source_course_geny','')
                if date in u:
                    from .rapprochement_v20_6 import index_from_anchors, rapprocher
                    local_candidates=index_from_anchors([{'href':u,'text':''}],date)
                    decision=rapprocher(c,local_candidates)
                    match=(decision.get('statut')=='CORRESPONDANCE_CONFIRMEE'
                           and f"GENY-{decision['geny_id']}"==str(block.get('course_id')))
                if match:
                    correspondences[f'{date}_{key}']=block['course_id']
                    save(correspondences_path,correspondences)
            if match:
                manifest,manifest_path=m,f;break
        # Conserver l'identification certaine meme si la collecte de fiche est differee.
        decision=decisions_geny.get(key)
        if decision and decision.get('statut')=='CORRESPONDANCE_CONFIRMEE' and decision.get('geny_id'):
            expected_cid=f"GENY-{decision['geny_id']}"
            if correspondences.get(f'{date}_{key}')!=expected_cid:
                correspondences[f'{date}_{key}']=expected_cid
                save(correspondences_path,correspondences)
        # Correspondance explicite PMU RnCn -> Geny : jamais sur le seul numéro de course.
        if manifest is None and not est_partie:
            # Le worker résout une fiche exacte à la fois. Ne plus ouvrir toutes
            # les fiches pour découvrir un manifeste avant de commencer la collecte.
            entry['historique_geny']='FILE_INCREMENTALE_INDEPENDANTE'
        # Recuperer l'arrivee PMU meme lorsque Geny est indisponible ou non associe.
        # Ce traitement n'engendre jamais de prevision apres le depart.
        if manifest is None and est_partie:
            try:
                if pmu_participants is None:
                    raise ValueError(error or 'PARTICIPANTS_PMU_ABSENTS')
                from .resultats_v18 import enregistrer_resultats
                entry['statut_arrivee']=enregistrer_resultats(cache,c,pmu_participants,observe=observed)
                entry['etat']='ARRIVEE_PMU_SANS_GENY'
            except Exception as exc:
                entry['statut_arrivee']='ARRIVEE_NON_VERIFIEE'
                entry['erreur_arrivee']=f'{type(exc).__name__}: {exc}'
        if manifest is None:
            if not est_partie:entry['etat']='GENY_NON_ASSOCIE'
            entry['motif_attente_geny']=('COOLDOWN_GENY' if cooldown else
                'QUOTA_DECOUVERTE_ATTEINT' if remaining_discoveries<=0 else
                entry.get('erreur_decouverte','AUCUNE_ASSOCIATION_VERIFIEE'))
            continue
        entry['identifiant_geny']=manifest['courses'][0]['course_id'];entry['etat']='MANIFESTE_PRESENT'
        # Le cycle de décision utilise le cache ; le worker enrichit la file séparément.
        if not est_partie:
            entry['historique_geny']='FILE_INCREMENTALE_INDEPENDANTE'
        raw=None
        # La veille, ne pas saturer PMU en consultant les participants de toutes
        # les courses: les controles NP recommencent le jour J.
        verifier_participants=est_partie or (departure-now)<=timedelta(hours=6) or date>now.astimezone(PARIS).date().isoformat()
        try:
            if not verifier_participants: raise LookupError('CONTROLE_NP_DIFFERE_JUSQU_A_H6')
            if pmu_participants is None:
                raise ValueError(error or 'PARTICIPANTS_PMU_ABSENTS')
            raw = pmu_participants
            # Une course passée ne reçoit plus de nouvelles vérifications NP.
            # Les données brutes servent uniquement à confirmer l'arrivée.
            if fenetre_decision:
                info=update_np(cache,c,manifest,raw)
                entry['np_confirmes']=sum(x['statut_participation']=='NON_PARTANT' for x in info['chevaux'])
                entry['np_verification_utc']=info['date_controle_utc']
        except Exception as exc:
            if isinstance(exc,LookupError): entry['statut_np']='CONTROLE_DIFFERE'
            else: entry['erreur_np']=f'{type(exc).__name__}: {exc}'
        if est_partie and raw is not None:
            try:
                from .resultats_v18 import enregistrer_resultats
                entry['statut_arrivee']=enregistrer_resultats(cache,c,raw,observe=observed)
            except (NameError,ValueError,TypeError) as exc:
                entry['statut_arrivee']='ARRIVEE_NON_VERIFIEE'
                entry['erreur_arrivee']=str(exc)
        if fenetre_decision:
            try:
                from .pronostics_v18 import preparer_top3, actualiser_top3_np
                entry['statut_prevision']=preparer_top3(cache,c,manifest)
                entry['statut_maj_np']=actualiser_top3_np(cache,c,manifest)
            except Exception as exc:
                entry['statut_prevision']='ERREUR_MODELE_PROVISOIRE'
                entry['erreur_prevision']=str(exc)
        try:
            exporter(manifest,cache,cache/'exports')
            from .ml_v19 import export_comparatif
            entry['comparatif_csv']=str(export_comparatif(cache,c,manifest))
            from .audit_predictif_v20_1 import analyser_course, bilan_global
            entry['audit_predictif']=analyser_course(cache,c,manifest)
            if entry['audit_predictif']=='AUDIT_ENREGISTRE':
                entry['bilan_audits_csv']=bilan_global(cache)
        except Exception as exc:entry['erreur_export']=str(exc)
    state['fiches_geny_budget_consommees']=max_new-remaining_new
    save(index,state)
    if not production:
        from .historiques_incrementaux import alimenter
        alimenter(cache, now)
    print(json.dumps({'date':date,'courses_pmu':len(courses),'courses_selectionnees':len(selected),
                      'manifestes_associes':sum(e.get('identifiant_geny') is not None for e in state['courses'].values()),
                      'rapprochements_ambigus':sum(e.get('rapprochement_geny',{}).get('statut')=='CORRESPONDANCE_AMBIGUE' for e in state['courses'].values()),
                      'alertes':state['alertes'][-3:]},ensure_ascii=False))
    return state

def main():
    p=argparse.ArgumentParser();p.add_argument('--cache',default='cache_pmu');p.add_argument('--date',default='')
    p.add_argument('--courses',default='',help='Ex R2C8,R1C4; vide = toutes');p.add_argument('--max-nouvelles-fiches',type=int,default=6)
    p.add_argument('--max-decouvertes',type=int,default=2)
    a=p.parse_args();date=a.date or datetime.now(PARIS).date().isoformat()
    if a.max_nouvelles_fiches<0 or a.max_nouvelles_fiches>30:p.error('Nombre de fiches invalide')
    run(Path(a.cache),date,[x.strip().upper() for x in a.courses.split(',') if x.strip()],a.max_nouvelles_fiches,max_discoveries=a.max_decouvertes)
if __name__=='__main__':main()

