"""PMU V19: features temporelles, apprentissage supervisé et audit sans fuite de cote.

Source d'apprentissage: instantanés de *prévisions antérieures au départ* et
arrivées PMU vérifiées; aucune reconstitution a posteriori des variables.
Les cotes, rapports, prix et rangs à l'arrivée ne sont JAMAIS des features.
"""
from __future__ import annotations
import csv, hashlib, json, math, re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from collections import defaultdict

from .profils_partants import SIGNAUX_PROFILS

FEATURES = ('courses_30j','courses_60j','courses_120j','podiums_30j','podiums_120j',
            'victoires_120j','disqualifications_120j','score_forme','forme_30j','forme_ancien',
            'jours_repos','distance_m','distance_ecart_m','aptitude_hippodrome',
            'taux_podium_distance','nb_partants','meteo_pluie_mm','meteo_vent_kmh','meteo_temperature_c','meteo_humidite_pct',
            'avis_experts_score','info_ecurie_score','driver_score','entraineur_score','pmu_score_direct',
            'age_ans','gains_euros','sexe_male','sexe_femelle','sexe_hongre',
            'ferrure_d4','ferrure_dp','ferrure_da','ferrure_p4','ferrure_pa','ferrure_pp')
LEGACY_FEATURES = FEATURES
FEATURES += ('discipline_montee', 'forme_pmu_discipline', 'forme_geny_comparable')
MODEL_SCHEMA = 'pmu-podium-v34'
ACTIVE_MODEL_SCHEMA = 'pmu-podium-actif-v1'
FERRURE_RESEARCH = ('forme_ferrure_neutre', 'forme_ferrure_moderee', 'forme_ferrure_actuelle')
CHRONO_RESEARCH = ('chrono_comparable_mediane_sec_km', 'chrono_comparable_nb_sorties')
DEPART_RESEARCH = {
    'Position absolue autostart': ('position_autostart_absolue',),
    'Mode de départ et distance': ('depart_autostart', 'distance_autostart'),
    'Position et ligne autostart': ('position_autostart_relative', 'ligne_autostart'),
    'Forme Geny par mode de départ': ('forme_geny_meme_depart', 'sorties_geny_meme_depart'),
    'Recul au départ': ('recul_depart_m',),
}
OPTIONAL_FEATURES = (*FERRURE_RESEARCH, *CHRONO_RESEARCH, 'tandem_podium_lisse', 'tandem_courses', 'avis_pmu_structure',
                     *(field for fields in DEPART_RESEARCH.values() for field in fields))
ACTIVE_FEATURES = (*FEATURES, *OPTIONAL_FEATURES, *SIGNAUX_PROFILS,
                   'sorties_geny_comparables_120j', 'ferrures_historiques_comparees')


def load(path, default=None):
    try: return json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError, ValueError): return default

def save(path, doc):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(doc,ensure_ascii=False,indent=2),encoding='utf-8');tmp.replace(path)

def numeric(v):
    try:
        x=float(str(v).replace(',','.'))
        return x if math.isfinite(x) else None
    except (ValueError,TypeError): return None

def features(horse, history, course, context=None, *, legacy=False):
    """Strictement les informations antérieures à la course; champs absents = None."""
    from .formes_contextuelles_v32 import _classement, _discipline
    context=context or {}
    discipline = None if legacy else _discipline(course.get('discipline'))
    departure=datetime.fromisoformat(course['depart'])
    date=departure.date()
    rows=[]
    seen=set()
    for p in history.get('performances',[]):
        try: d=datetime.fromisoformat(p['date']).date()
        except (KeyError,ValueError,TypeError):continue
        age=(date-d).days
        if age<=0 or age>730:continue
        if discipline and _discipline(p.get('discipline')) != discipline:
            continue
        rank=str(p.get('classement','')).strip().casefold()
        dist=numeric(p.get('distance_m'))
        if legacy:
            num = int(rank) if rank.isdecimal() else None
        else:
            if _classement(rank) is None:
                continue
            match = re.match(r'^[1-9][0-9]*', rank)
            num = int(match[0]) if match else None
            identity = (d, str(p.get('hippodrome', '')).casefold(), dist, rank)
            if identity in seen:
                continue
            seen.add(identity)
        rows.append((age,num,rank.casefold(),dist,str(p.get('hippodrome','')).casefold()))
    def pts(rank):return {1:5.,2:3.5,3:2.5,4:1.3,5:1.}.get(rank,0.)
    recent=[r for r in rows if r[0]<=120]
    early=[r for r in rows if 30<r[0]<=120]
    last=[r for r in rows if r[0]<=30]
    target_dist=numeric(course.get('distance_m'))
    target_hip=str(course.get('hippodrome','')).casefold()
    comparable=[r for r in rows if target_dist is not None and r[3] is not None and abs(r[3]-target_dist)<=250]
    hip=[r for r in rows if target_hip and target_hip in r[4]]
    def avg(seq):return round(sum(pts(r[1]) for r in seq)/len(seq),5) if seq else None
    def pct(seq):return round(sum(r[1] is not None and r[1]<=3 for r in seq)/len(seq),5) if seq else None
    # Données contextuelles acceptées uniquement si provenance et heure de collecte valides.
    out={
      'courses_30j':len(last),'courses_60j':sum(r[0]<=60 for r in recent),
      'courses_120j':len(recent),'podiums_30j':pct(last),'podiums_120j':pct(recent),
      'victoires_120j':sum(r[1]==1 for r in recent),
      'disqualifications_120j':sum(r[2] in ('dai','di','da','disq') for r in recent),
      'score_forme':avg(recent),'forme_30j':avg(last),'forme_ancien':avg(early),
      'jours_repos':min((r[0] for r in rows),default=None),
      'distance_m':target_dist,
      'discipline_montee': int(discipline == 'm') if discipline else None,
      'forme_geny_comparable':avg([r for r in comparable if r[0]<=120]),
      'distance_ecart_m':min((abs(r[3]-target_dist) for r in rows if r[3] is not None),default=None) if target_dist is not None else None,
      'aptitude_hippodrome':pct(hip),'taux_podium_distance':pct(comparable),
      'nb_partants':numeric(course.get('nombre_declares')),
    }
    if not legacy and not history:
        for key in ('courses_30j','courses_60j','courses_120j','victoires_120j','disqualifications_120j'):
            out[key] = None
    if not legacy and history and target_dist is not None:
        out['sorties_geny_comparables_120j'] = sum(r[0] <= 120 for r in comparable)
    for key in FEATURES:
        if key not in out:out[key]=numeric(context.get(key))
    return out

CONTEXT_FEATURES = frozenset({
    'meteo_pluie_mm', 'meteo_vent_kmh', 'meteo_temperature_c', 'meteo_humidite_pct',
    'avis_experts_score', 'info_ecurie_score',
})


def _valid_context(cache,course,now,*,legacy=False):
    """Contexte facultatif saisi/importé et sourcé, antérieur au départ."""
    path=Path(cache)/'contextes'/f"{course['date']}_{course['code']}.json"
    d=load(path,{}) or {}; results={}
    for item in d.get('observations',[]):
        if not isinstance(item,dict):continue
        key=item.get('champ'); value=numeric(item.get('valeur'))
        try: stamp=datetime.fromisoformat(item['collecte_utc'])
        except (KeyError,TypeError,ValueError):continue
        url = item.get('source_url')
        if stamp.tzinfo is None or not isinstance(url, str) or not url.startswith(('https://', 'http://')):
            continue
        if stamp>now or stamp>=datetime.fromisoformat(course['depart']):continue
        if key in (LEGACY_FEATURES if legacy else CONTEXT_FEATURES) and value is not None:
            # Pour les observations individuelles, prioriser l'index du cheval.
            numero=item.get('numero')
            results[(str(numero) if numero is not None else '*',key)]=value
    return results

def snapshot(cache,course,manifest,now=None):
    """Capture immuable pré-départ; ne remplace jamais une capture existante."""
    now=now or datetime.now(timezone.utc)
    departure=datetime.fromisoformat(course['depart'])
    if now>=departure:return 'TROP_TARD'
    base=Path(cache)/'ml'/'instantanes'/f"{course['date']}_{course['code']}.json"
    if base.exists():return 'DEJA_CAPTURE'
    cid=manifest['courses'][0]['course_id']
    np=load(Path(cache)/'participations'/f'{cid}.json',{}) or {}
    states={str(x.get('numero')):x.get('statut_participation') for x in np.get('chevaux',[])}
    eligible=[h for h in manifest['courses'][0]['partants'] if states.get(str(h['numero']))=='PARTANT']
    if len(eligible)<3:return 'NP_NON_VERIFIE'
    if len(states)!=len(manifest['courses'][0]['partants']) or any(x not in ('PARTANT','NON_PARTANT') for x in states.values()):return 'NP_NON_VERIFIE'
    context=_valid_context(cache,course,now)
    rows=[]
    for h in eligible:
        doc=load(Path(cache)/'historiques'/str(h['id'])/'historique_geny.json',{}) or {}
        c={key:v for (num,key),v in context.items() if num in ('*',str(h['numero']))}
        rows.append({'numero':int(h['numero']),'cheval_id':str(h['id']),'nom':h['nom'],
                     'features':features(h,doc,course,c)})
    save(base,{'date':course['date'],'code':course['code'],'depart':course['depart'],
               'capture_utc':now.isoformat(),'features_schema':'v19.1','chevaux':rows,
               'regle':'snapshot anterieur au depart; cotes et arrivees exclues des features'})
    return 'CAPTURE'


def pmu_rows(cache,course,raw,now,*,legacy=False):
    """Meme extraction PMU pour capture et inference; aucune requete reseau."""
    from .auto_v18 import _list, _num
    from .formes_contextuelles_v32 import (
        _discipline, _historique_contextuel, _musique_pmu, chronos_comparables, forme_meme_depart,
    )
    from .echeances_production import instant
    from .partants_actuels_v21 import extraire_partants, ferrure_normalisee
    from .top3_independants_v22 import _form_score
    from .profils_partants import evaluer_profils
    from .signaux_geny import signaux
    cache=Path(cache)
    participants=_list(raw,'participants','partants')
    if len(participants)<3:return 'PARTANTS_INSUFFISANTS',[],{}
    from .liaison_chevaux_v22 import etablir, nom_normalise
    profils=extraire_partants(raw, course=course if not legacy else None)
    names=[{'numero':numero,'nom':profil['nom']}
           for numero,profil in profils.items() if profil.get('nom')]
    association=etablir(cache,course,names)
    context=_valid_context(cache,course,now,legacy=legacy)
    discipline = _discipline(course.get('discipline'))
    has_connections = any(p.get('driver_jockey') or p.get('entraineur') for p in profils.values())
    connection_scores = scores_intervenants(cache, now, discipline) if (
        not legacy and discipline and has_connections) else {}
    from .avis_experts_v22 import POSITIVE
    rows=[];seen=set();with_history=0;with_partial=0;unknown_np=0
    for item in participants:
        if not isinstance(item,dict):continue
        numero=_num(item,'numPmu','num','numero','numeroPmu')
        if numero is None or numero in seen:return 'NUMEROS_PMU_INCOHERENTS',[],{}
        seen.add(numero)
        if item.get('nonPartant') is True or str(item.get('statut','')).upper() in ('NP','NON_PARTANT'):
            continue
        if item.get('nonPartant') is not False and str(item.get('statut','')).upper()!='PARTANT':
            unknown_np+=1
        profil=profils.get(numero,{})
        horse_name=profil.get('nom')
        if not horse_name:return 'IDENTITE_PMU_ABSENTE',[],{}
        link=association.get(str(numero),{})
        ident,histo=link.get('cheval_id',''),link.get('historique',{})
        historical_stamp = instant(histo.get('extrait_utc'))
        # La date d'une performance ne prouve pas la disponibilité de sa fiche.
        if not legacy and (not str(histo.get('source_url', '')).startswith(('https://www.geny.com/', 'https://geny.com/')) or not historical_stamp or historical_stamp > now):
            histo = {}
        if ident and histo:
            if histo.get('statut')=='PARTIEL_HISTORIQUE':with_partial+=1
            else:with_history+=1
        c = {key: value for (num, key), value in context.items() if num == '*'}
        c.update({key: value for (num, key), value in context.items() if num == str(numero)})
        direct = _form_score(item)
        if direct is not None:
            c['pmu_score_direct'] = direct
        if not legacy:
            c['forme_pmu_discipline'] = _musique_pmu(item, discipline)[0]
        intervenants = {role: nom_normalise(profil.get(field))
                        for role, field in (('driver_score', 'driver_jockey'), ('entraineur_score', 'entraineur'))
                        if profil.get(field)}
        if not legacy:
            for role, person in intervenants.items():
                if (role, person) in connection_scores:
                    c[role] = connection_scores[role, person]
        for feature in ('age_ans','gains_euros'):
            value=profil.get(feature)
            if value is not None:c[feature]=value
        sexe=profil.get('sexe','')
        if sexe:
            for label,feature in (('Mâle','sexe_male'),('Femelle','sexe_femelle'),('Hongre','sexe_hongre')):
                c[feature]=1 if sexe==label else 0
        ferrure = profil.get('ferrure', '')
        if not legacy:
            ferrure = ferrure_normalisee(ferrure)
        if ferrure:
            code=str(ferrure).upper()
            for ferrure_code,indicator in [('D4','ferrure_d4'),('DP','ferrure_dp'),
                                   ('DA','ferrure_da'),('P4','ferrure_p4'),
                                   ('PA','ferrure_pa'),('PP','ferrure_pp')]:
                c[indicator]=1 if ferrure_code in code.split('/') else 0
        research = {}
        if not legacy:
            profils_course = evaluer_profils(course, {**link, 'historique': histo}, profil, now)
            research.update({key: int(profils_course[key]) for key in SIGNAUX_PROFILS
                             if profils_course[key] is not None})
            depart_trot = profil.get('depart_trot', {})
            if depart_trot.get('mode'):
                auto = int(depart_trot['mode'] == 'Autostart')
                research['depart_autostart'] = auto
                distance = numeric(course.get('distance_m'))
                if distance is not None:
                    research['distance_autostart'] = auto * distance
            if depart_trot.get('mode') == 'Autostart' and depart_trot.get('position'):
                research['position_autostart_absolue'] = depart_trot['position']
            if depart_trot.get('ligne'):
                capacity = depart_trot['capacite']
                research['ligne_autostart'] = depart_trot['ligne']
                research['position_autostart_relative'] = ((depart_trot['position'] - 1) % capacity) / capacity
            if 'recul_m' in depart_trot:
                research['recul_depart_m'] = depart_trot['recul_m']
            if histo:
                research.update(chronos_comparables(histo, course))
                research.update(signaux(course, profil, {**link, 'historique': histo}, now))
            same_mode = forme_meme_depart(histo, course, profil, now)
            if same_mode:
                research.update(forme_geny_meme_depart=same_mode['score'],
                                sorties_geny_meme_depart=same_mode['performances_valides'])
            driver = intervenants.get('driver_score')
            tandem = connection_scores.get(('tandem', ident, nom_normalise(horse_name), driver))
            if tandem:
                research.update(tandem_podium_lisse=tandem[0], tandem_courses=tandem[1])
            if histo and discipline and ferrure:
                for key, different, unknown in zip(FERRURE_RESEARCH, (1., .8, .65), (1., .9, .85)):
                    shape = _historique_contextuel(histo, course, {'ferrure': ferrure},
                                                  ferrure_differente=different, ferrure_inconnue=unknown)
                    if shape and shape['ferrures_comparees']:
                        research[key] = shape['score']
                        research['ferrures_historiques_comparees'] = shape['ferrures_comparees']
            opinion = item.get('avisEntraineur')
            if isinstance(opinion, dict):
                label = str(opinion.get('type') or opinion.get('libelle') or '').strip().casefold()
                value = {'NEGATIF': -1, 'NEUTRE': 0, 'POSITIF': 1}.get(POSITIVE.get(label))
                if value is not None:
                    research['avis_pmu_structure'] = value
        features_values=features({'numero':numero,'nom':horse_name},histo,course,c,legacy=legacy)
        rows.append({'numero':numero,'cheval_id':ident,'nom':horse_name,
                     'historique_ok':bool(histo),'historique_complet':bool(histo) and histo.get('statut')=='COMPLET',
                     'methode_liaison':link.get('methode','NON_ASSOCIE'),
                     'source_historique':histo.get('source_url'),
                     'historique_extrait_utc':histo.get('extrait_utc'),
                     'intervenants_pmu':intervenants,
                     'score_direct_pmu':direct,
                     'features':{**features_values, **research}})
    if len(rows)<3:return 'PARTANTS_INSUFFISANTS',[],{}
    if course.get('nombre_declares') and len(seen)!=int(course['nombre_declares']):
        return 'LISTE_PARTANTS_INCOMPLETE',[],{}
    return 'OK',rows,{'historiques_complets_reutilises':with_history,
                      'historiques_partiels_reutilises':with_partial,'np_non_verifies':unknown_np}


def snapshot_pmu(cache,course,raw,now=None,clock=None,*,prepared=None):
    """Capture immutable; les anciennes captures ne sont jamais enrichies apres coup."""
    now=now or datetime.now(timezone.utc)
    departure=datetime.fromisoformat(course['depart'])
    if now.tzinfo is None or departure.tzinfo is None or now>=departure:return 'TROP_TARD'
    base=Path(cache)/'ml'/'instantanes'/f"{course['date']}_{course['code']}.json"
    if base.exists():return 'DEJA_CAPTURE'
    status,rows,metadata=prepared if prepared is not None else pmu_rows(cache,course,raw,now)
    if status!='OK':return status
    if metadata['np_non_verifies']:return 'NP_NON_VERIFIE'
    captured=clock() if clock else now
    if captured>=departure:return 'TROP_TARD'
    save(base,{'date':course['date'],'code':course['code'],'depart':course['depart'],
               'capture_utc':captured.astimezone(timezone.utc).isoformat(),
               'observation_utc':now.astimezone(timezone.utc).isoformat(),'features_schema':MODEL_SCHEMA,
               'source':'PMU_API_PARTICIPANTS','nombre_chevaux':len(rows),
               **metadata,'chevaux':rows,
               'regle':'capture PMU pre-depart immutable, ni cote ni arrivee utilisee'})
    return 'CAPTURE_PMU'

def dataset(cache, now=None):
    """Exemples pre-depart avec podium complet et labels deja observes."""
    now=now or datetime.now(timezone.utc)
    examples=[];course_count=0
    for snap in sorted((Path(cache)/'ml'/'instantanes').glob('*.json')):
        s=load(snap,{}) or {};arr=load(Path(cache)/'arrivees'/snap.name,{}) or {}
        try:
            depart=datetime.fromisoformat(s['depart']);capt=datetime.fromisoformat(s['capture_utc'])
            checked=datetime.fromisoformat(arr['verifie_utc'])
            if any(t.tzinfo is None for t in (depart,capt,checked,now)):continue
            if not capt<depart<checked<=now or s.get('np_non_verifies',0):continue
            if arr.get('source') not in (None, 'PMU_API_PARTICIPANTS'):
                continue
            key=s['date']+'_'+s['code']
            if snap.stem!=key or arr.get('date',s['date'])!=s['date'] or arr.get('course',s['code'])!=s['code']:continue
            podium=[x for x in arr.get('arrivee',[]) if x.get('rang') in (1,2,3)]
            placed={int(x['numero']) for x in podium}
            if len(podium)!=3 or len(placed)!=3 or {x['rang'] for x in podium}!={1,2,3}:continue
            horses=s.get('chevaux',[]);numbers={int(x['numero']) for x in horses}
            if len(horses)<3 or len(numbers)!=len(horses) or not placed<=numbers:continue
            if any(not isinstance(x.get('features'),dict) for x in horses):continue
        except (AttributeError,KeyError,ValueError,TypeError):continue
        observed_raw = s.get('observation_utc', s['capture_utc'])
        from .echeances_production import instant
        observed = instant(observed_raw)
        if not observed or observed > capt:
            continue
        course_count+=1
        for row in horses:
            examples.append({'course':key,'depart':s['depart'],'capture_utc':s['capture_utc'],
                'verifie_utc':arr['verifie_utc'],'observation_utc':observed_raw,'numero':int(row['numero']),
                'cheval_id':str(row.get('cheval_id') or ''),'nom':row.get('nom'),
                'capture_qualifiante': s.get('features_schema') == MODEL_SCHEMA
                    and s.get('source') == 'PMU_API_PARTICIPANTS'
                    and arr.get('source') == 'PMU_API_PARTICIPANTS',
                'y':int(int(row['numero']) in placed),
                'intervenants_pmu': row.get('intervenants_pmu', {}),
                'features':row['features'] if s.get('features_schema') == MODEL_SCHEMA else
                    {k: row['features'][k] for k in ('pmu_score_direct', 'distance_m', 'age_ans', 'gains_euros',
                     'sexe_male', 'sexe_femelle', 'sexe_hongre') if k in row['features']}})
    return examples,course_count


def scores_intervenants(cache, now, discipline):
    """Taux de podium lissé sur les captures PMU vérifiées des 90 derniers jours."""
    window = now - timedelta(days=90)
    records, _ = dataset(cache, now)
    from .liaison_chevaux_v22 import nom_normalise
    groups = defaultdict(list)
    tandems = defaultdict(dict)
    for row in records:
        if (not row['capture_qualifiante'] or datetime.fromisoformat(row['depart']) < window
                or numeric(row['features'].get('discipline_montee')) != int(discipline == 'm')):
            continue
        identities = row['intervenants_pmu']
        if not isinstance(identities, dict):
            continue
        for role in ('driver_score', 'entraineur_score'):
            name = identities.get(role)
            if isinstance(name, str) and name:
                groups[role, name].append(row)
        driver = identities.get('driver_score')
        horse = nom_normalise(row.get('nom'))
        # Les anciennes captures peuvent porter le nom d'un intervenant.
        # Elles restent exploitables pour les taux par rôle.
        if (row['cheval_id'] and horse and horse not in identities.values()
                and isinstance(driver, str) and driver):
            tandems['tandem', row['cheval_id'], horse, driver][row['course']] = row['y']
    scores = {key: (sum(row['y'] for row in rows) + 1) / (len(rows) + 5)
              for key, rows in groups.items()
              if len(rows) >= 5 and len({row['course'] for row in rows}) >= 2}
    for key, results in tandems.items():
        prior = scores.get(('driver_score', key[-1]), .2)
        scores[key] = ((sum(results.values()) + 5 * prior) / (len(results) + 5), len(results))
    return scores


def train(cache, min_courses=None, min_rows=None, now=None):
    """Figer un candidat puis appliquer une décision sur une cohorte prospective."""
    from .maturite_ml import (CANDIDATE, REPORT, candidate_path, comparisons, coverage,
                             prospective, sha, thresholds)
    import shutil

    now = now or datetime.now(timezone.utc)
    cache = Path(cache)
    limits = thresholds()
    pre, prod = limits['PREPRODUCTION'], limits['PRODUCTION']
    records, n = dataset(cache, now)
    qualifying = [row for row in records if row['capture_qualifiante']]
    quality = coverage(qualifying)
    qualified_courses = len({row['course'] for row in qualifying})
    minimum_courses = pre['courses'] if min_courses is None else min_courses
    minimum_rows = pre['observations'] if min_rows is None else min_rows
    live = cache / 'ml/modele.joblib'
    status = {'entrainement_utc': now.isoformat(), 'courses': n, 'lignes': len(records),
              'minimum_courses': minimum_courses, 'minimum_lignes': minimum_rows,
              'courses_qualifiantes': qualified_courses, 'observations_qualifiantes': len(qualifying),
              'seuils': limits, 'couverture': quality, 'etat': 'INSUFFISANT',
              'maturite': 'EXPÉRIMENTAL', 'promotion_production': False}

    def finish():
        if live.is_file():
            status['version_en_service'] = sha(live)
            decision = load(cache / 'ml/preuve_promotion.json', {}) or {}
            status['maturite_en_service'] = ('PRODUCTION VALIDÉE' if
                decision.get('sha256') == status['version_en_service'] else 'MODÈLE HISTORIQUE')
        save(cache / REPORT, status)
        save(cache / 'ml/entrainement.json', status)
        return status

    candidate = load(cache / CANDIDATE, {}) or {}
    path = candidate_path(cache, candidate)
    if candidate and path is None:
        status['etat'] = 'CANDIDAT_INTEGRITE_INVALIDE'
        return finish()
    if candidate and candidate.get('decision') == 'ACCEPTE':
        # Reprise sûre si l'écriture de la preuve et la mise en service ont été interrompues.
        proof_path = cache / 'ml/preuve_promotion.json'
        if not live.is_file() or sha(live) != candidate['sha256']:
            temporary = live.with_suffix('.tmp')
            shutil.copyfile(path, temporary)
            temporary.replace(live)
        save(proof_path, candidate)
        status.update(etat='ENTRAINE', maturite='PRODUCTION VALIDÉE',
                      version=candidate['sha256'], prospective=candidate['prospective'])
        if n < candidate['courses_a_la_decision'] + prod['prospectives']:
            return finish()
        candidate = {}
    if candidate and candidate.get('decision') == 'REJETE':
        status.update(etat='NON_PROMU_AVANTAGE_NON_DEMONTRE', version=candidate['sha256'],
                      prospective=candidate['prospective'])
        # Une nouvelle génération exige au moins une nouvelle cohorte de données.
        if n < candidate['courses_a_la_decision'] + prod['prospectives']:
            return finish()
        candidate = {}

    if not candidate:
        if qualified_courses < minimum_courses or len(qualifying) < minimum_rows:
            return finish()
        if quality['completude'] < pre['completude']:
            status['etat'] = 'COMPLETUDE_INSUFFISANTE'
            return finish()
        days = sorted({r['course'][:10] for r in records})
        if len(days) < 3:
            status['etat'] = 'PERIODES_TEMPORELLES_INSUFFISANTES'
            return finish()
        try:
            import joblib
            from .experience_ml import run
        except ImportError:
            status['etat'] = 'DEPENDANCES_ML_ABSENTES'
            return finish()
        output = cache / 'ml/experiences' / now.astimezone(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
        try:
            report = run(cache, output, days[-2], days[-1], now=now, select_research=True)
        except ValueError as exc:
            status.update(etat='VALIDATION_TEMPORELLE_IMPOSSIBLE', motif=str(exc))
            return finish()
        artifact = output / 'modele_experimental.joblib'
        if (report['apprentissage_final']['courses'] < minimum_courses
                or report['apprentissage_final']['observations'] < minimum_rows
                or report['apprentissage_final']['completude'] < pre['completude']):
            status.update(etat='APPRENTISSAGE_FINAL_INSUFFISANT',
                          apprentissage_final=report['apprentissage_final'])
            return finish()
        packed = joblib.load(artifact)
        packed.update(statut='ML_ENTRAINE_NON_CALIBRE', entrainement_utc=now.isoformat(),
                      dernier_label_entrainement_utc=report['dernier_label_entrainement_avant_test'])
        joblib.dump(packed, artifact)
        digest = sha(artifact)
        path = cache / 'ml/candidats' / digest / 'modele.joblib'
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(artifact, path)
        candidate = {'sha256': digest, 'entrainement_utc': now.isoformat(),
                     'dernier_label_entrainement_utc': packed['dernier_label_entrainement_utc'],
                     'modele': packed['modele'], 'seuils': limits,
                     'apprentissage_final': report['apprentissage_final'],
                     'rapport': str(output.relative_to(cache) / 'rapport.json')}
        save(cache / CANDIDATE, candidate)

    # Les paramètres de décision d'une cohorte restent ceux de son lancement.
    pre, prod = (candidate['seuils'][key] for key in ('PREPRODUCTION', 'PRODUCTION'))
    rows = comparisons(cache, candidate, now)
    result = prospective(rows[:prod['prospectives']])
    status.update(etat='EVALUATION_PROSPECTIVE', version=candidate['sha256'],
                  rapport=candidate['rapport'], modele=candidate['modele'],
                  seuils=candidate['seuils'], prospective=result,
                  apprentissage_final=candidate['apprentissage_final'])
    if result['courses'] >= pre['prospectives'] and result['completude'] >= pre['completude']:
        status['maturite'] = 'PRÉPRODUCTION'
    if (qualified_courses < prod['courses'] or len(qualifying) < prod['observations']
            or quality['completude'] < prod['completude'] or result['courses'] < prod['prospectives']):
        return finish()
    accepted = (result['completude'] >= prod['completude']
                and result['comparaison']['ic95_bootstrap_par_course'][0] > 0)
    candidate.update(decision='ACCEPTE' if accepted else 'REJETE', decision_utc=now.isoformat(),
                     courses_a_la_decision=n, prospective=result,
                     preuve=rows[:prod['prospectives']])
    save(cache / CANDIDATE, candidate)
    if accepted:
        temporary = live.with_suffix('.tmp')
        shutil.copyfile(path, temporary)
        temporary.replace(live)
        save(cache / 'ml/preuve_promotion.json', candidate)
        status.update(etat='ENTRAINE', maturite='PRODUCTION VALIDÉE', promotion_production=True)
    else:
        status.update(etat='NON_PROMU_AVANTAGE_NON_DEMONTRE', maturite='EXPÉRIMENTAL')
    return finish()


def ranking_for(packed, rows):
    import numpy as np

    vectors = [[numeric(h['features'].get(k)) if numeric(h['features'].get(k)) is not None
                else float('nan') for k in packed['features']] for h in rows]
    scores = packed['model'].predict_proba(np.asarray(vectors))[:, 1]
    ranking = [{'numero': h['numero'], 'nom': h['nom'], 'cheval_id': h['cheval_id'],
                'score_non_calibre': round(float(score), 5)} for h, score in zip(rows, scores)]
    return sorted(ranking, key=lambda h: (-h['score_non_calibre'], h['numero']))


def predict_pmu(cache,course,raw,now=None,clock=None,*,prepared=None):
    """Inférence pré-départ : modèle promu, sinon candidat expérimental explicite."""
    from .planification_v20_2 import decision_autorisee
    now=now or datetime.now(timezone.utc)
    departure=datetime.fromisoformat(course['depart'])
    if not decision_autorisee(now,course['date'],departure):return 'HORS_FENETRE_DECISION'
    path=Path(cache)/'ml'/'modele.joblib'
    experimental=False
    if not path.exists():
        from .cycle_ml_actif import modele_disponible
        path=modele_disponible(cache)
        if path is None:return 'ML_NON_ENTRAINE'
        experimental=True
    try:
        import joblib
        packed=joblib.load(path)
    except (ImportError,OSError,ValueError,KeyError) as exc:return f'MODELE_INDISPONIBLE_{type(exc).__name__}'
    signature = packed.get('schema'), tuple(packed.get('features', ()))
    schema, fields = signature
    added = fields[len(FEATURES):]
    supported = (schema == MODEL_SCHEMA and fields[:len(FEATURES)] == FEATURES
                 and len(set(added)) == len(added) and set(added) <= set(OPTIONAL_FEATURES)) or (
        signature == ('pmu-podium-v33', LEGACY_FEATURES)) or (
        experimental and signature == (ACTIVE_MODEL_SCHEMA, ACTIVE_FEATURES))
    if not supported:
        return 'MODELE_SCHEMA_OBSOLETE_REENTRAINEMENT_REQUIS'
    if experimental:
        from .cycle_ml_actif import STATUT
        if packed.get('statut')!=STATUT:return 'MODELE_EXPERIMENTAL_INVALIDE'
        try:
            fitted=datetime.fromisoformat(packed['entrainement_utc'])
            labelled=datetime.fromisoformat(packed['dernier_label_entrainement_utc'])
            if not labelled<=fitted<=now:return 'MODELE_EXPERIMENTAL_CHRONOLOGIE_INVALIDE'
        except (KeyError,TypeError,ValueError):return 'MODELE_EXPERIMENTAL_CHRONOLOGIE_INVALIDE'
    elif packed.get('statut')!='ML_ENTRAINE_NON_CALIBRE':return 'MODELE_NON_PROMU'
    elif packed.get('entrainement_utc'):
        from .echeances_production import instant
        fitted = instant(packed['entrainement_utc'])
        labelled = instant(packed.get('dernier_label_entrainement_utc'))
        if not fitted or not labelled or not labelled <= fitted <= now:
            return 'MODELE_CHRONOLOGIE_INVALIDE'
    legacy = schema == 'pmu-podium-v33'
    status, rows, metadata = (prepared if prepared is not None and not legacy
                              else pmu_rows(cache, course, raw, now, legacy=legacy))
    if status!='OK':return status
    if metadata['np_non_verifies']:return 'NP_NON_VERIFIE'
    ranking = ranking_for(packed, rows)
    created=clock() if clock else now
    if not decision_autorisee(created,course['date'],departure):return 'HORS_FENETRE_DECISION'
    base=Path(cache)/'pronostics'/f"{course['date']}_{course['code']}_ml_latest.json"
    old=load(base,{}) or {}
    if old.get('calcul_utc'):
        stamp=datetime.fromisoformat(old['calcul_utc']).astimezone(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
        archive=base.parent/'versions'/f"{course['date']}_{course['code']}_ml_{stamp}.json"
        if not archive.exists():save(archive,old)
    save(base,{'date':course['date'],'course':course['code'],'calcul_utc':created.astimezone(timezone.utc).isoformat(),
               'depart':course['depart'],'donnees_observees_utc':now.astimezone(timezone.utc).isoformat(),'modele':packed['modele'],'statut':packed['statut'],
               'experimental':experimental,'promotion_production':not experimental,
               'entrainement_utc':packed.get('entrainement_utc'),
               'dernier_label_entrainement_utc':packed.get('dernier_label_entrainement_utc'),
               'empreinte_modele':hashlib.sha256(path.read_bytes()).hexdigest(),
               'features_schema':packed['schema'],'variables_modele':list(fields),
               'couverture_variables':{field: sum(numeric(row['features'].get(field)) is not None
                                                   for row in rows) for field in fields},
               'entrees_modele':rows,
               'top3':ranking[:3],'classement_complet':ranking,
               'note':'Score non calibre; cotes exclues des variables.'})
    return 'ML_EXPERIMENTAL_CALCULE' if experimental else 'ML_CALCULE'


def predict(cache,course,manifest=None,now=None):
    """Compatibilite anciens appelants : relire exclusivement le profil PMU."""
    doc=load(Path(cache)/'partants_actuels'/f"{course['date']}_{course['code']}.json",{}) or {}
    raw={'participants':[{'numPmu':int(n),'nom':h.get('nom',''),'age':h.get('age_ans'),
        'gainsCarriere':h.get('gains_euros'),'sexe':h.get('sexe'),
        'ferrure':h.get('ferrure'),'musique':h.get('musique_pmu'),
        'statut':h.get('statut_np')} for n,h in doc.get('chevaux',{}).items()]}
    return predict_pmu(cache,course,raw,now)


def export_comparatif(cache,course,manifest):
    """CSV par partant: baseline, ML, NP, cote à l'approche du départ, arrivée."""
    key=f"{course['date']}_{course['code']}";cid=manifest['courses'][0]['course_id']
    base=load(Path(cache)/'pronostics'/f'{key}_top3.json',{}) or {}
    ml=load(Path(cache)/'pronostics'/f'{key}_ml_latest.json',{}) or {}
    baseline_final=load(Path(cache)/'pronostics'/f'{key}_baseline_latest.json',{}) or base
    np=load(Path(cache)/'participations'/f'{cid}.json',{}) or {}
    from .cotes_v19 import dernier_releve
    odds=dernier_releve(cache, course)
    arrived=load(Path(cache)/'arrivees'/f'{key}.json',{}) or {}
    b_rank={int(x['numero']):i for i,x in enumerate(base.get('classement_complet',[]),1)}
    bf_rank={int(x['numero']):i for i,x in enumerate(baseline_final.get('classement_complet',[]),1)}
    m_rank={int(x['numero']):i for i,x in enumerate(ml.get('classement_complet',[]),1)}
    m_proba={int(x['numero']):x.get('score_non_calibre',x.get('proba_podium_estimee')) for x in ml.get('classement_complet',[])}
    np_map={int(x['numero']):x for x in np.get('chevaux',[])}
    odd_map={int(x['numero']):x for x in odds.get('chevaux',[])}
    arank={int(x['numero']):x['rang'] for x in arrived.get('arrivee',[])}
    contexte=load(Path(cache)/'contextes'/f"{course['date']}_{course['code']}.json",{}) or {}
    meteo={x.get('champ'):x.get('valeur') for x in contexte.get('observations',[]) if isinstance(x,dict) and x.get('numero') is None}
    cols=['date','course','depart','numero','nom','statut_np','baseline_rang','baseline_top3',
          'baseline_final_rang','baseline_final_top3','ml_rang','ml_top3','ml_proba_podium','cote_avant_depart','cote_heure_utc',
          'cote_source','cote_statut','arrivee_rang','arrivee_podium','baseline_hits_course','baseline_final_hits_course',
          'ml_hits_course','ml_etat','version_baseline_utc','version_ml_utc','meteo_pluie_mm','meteo_vent_kmh','meteo_temperature_c','meteo_humidite_pct','meteo_capture_utc','meteo_source']
    ar3={n for n,r in arank.items() if r in (1,2,3)}
    baseline_hits=len(ar3&{n for n,v in b_rank.items() if v<=3}) if len(ar3)==3 and b_rank else ''
    baseline_final_hits=len(ar3&{n for n,v in bf_rank.items() if v<=3}) if len(ar3)==3 and bf_rank else ''
    ml_hits=len(ar3&{n for n,v in m_rank.items() if v<=3}) if len(ar3)==3 and m_rank else ''
    output=[]
    for h in manifest['courses'][0]['partants']:
        n=int(h['numero']);o=odd_map.get(n,{})
        output.append({'date':course['date'],'course':course['code'],'depart':course['depart'],
          'numero':n,'nom':h['nom'],'statut_np':np_map.get(n,{}).get('statut_participation','NP_NON_VERIFIE'),
          'baseline_rang':b_rank.get(n,''),'baseline_top3':'OUI' if n in b_rank and b_rank[n]<=3 else '',
          'baseline_final_rang':bf_rank.get(n,''),'baseline_final_top3':'OUI' if n in bf_rank and bf_rank[n]<=3 else '',
          'ml_rang':m_rank.get(n,''),'ml_top3':'OUI' if n in m_rank and m_rank[n]<=3 else '',
          'ml_proba_podium':m_proba.get(n,''),
          'cote_avant_depart':o.get('cote',''),'cote_heure_utc':o.get('heure_utc',''),
          'cote_source':o.get('source',''),'cote_statut':o.get('statut','NON_DISPONIBLE'),
          'arrivee_rang':arank.get(n,''),'arrivee_podium':'OUI' if n in ar3 else ('NON' if len(ar3)==3 else ''),
          'baseline_hits_course':baseline_hits,'baseline_final_hits_course':baseline_final_hits,'ml_hits_course':ml_hits,
          'ml_etat':ml.get('statut','ML_NON_ENTRAINE'),
          'version_baseline_utc':base.get('created_utc',''),'version_ml_utc':ml.get('calcul_utc',''),
          'meteo_pluie_mm':meteo.get('meteo_pluie_mm',''),'meteo_vent_kmh':meteo.get('meteo_vent_kmh',''),
          'meteo_temperature_c':meteo.get('meteo_temperature_c',''),'meteo_humidite_pct':meteo.get('meteo_humidite_pct',''),
          'meteo_capture_utc':contexte.get('meteo_collecte_utc',''),'meteo_source':contexte.get('meteo_source','')})
    path=Path(cache)/'exports'/cid/'comparatif_predictions.csv';path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('w',newline='',encoding='utf-8-sig') as f:
        w=csv.DictWriter(f,fieldnames=cols,delimiter=';');w.writeheader();w.writerows(output)
    return path

# Les cotes sont EXCLUES explicitement de FEATURES et des modèles.
assert not any('cote' in x or 'rapport' in x or 'arrivee' in x for x in FEATURES)
