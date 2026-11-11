"""Synchronisation idempotente pmu-data -> Google Sheets (3 onglets existants).

Aucune information inventée; les champs absents restent vides. Utilise un compte de service
partagé comme éditeur sur le Google Sheet. Les secrets ne sont jamais loggés.
"""
import csv
import hashlib
import json
import os
import re
import sys
from pathlib import Path
from datetime import datetime, timezone

SHEET_TABS = ('Courses & Prévisions', 'Historique chevaux', 'Résultats & Analyse')
# Nouvelle base visuelle : ne pas republier les anciennes courses apres le nettoyage.
# Les fichiers bruts, les audits et tous les historiques sont conserves dans pmu-data.
LIVE_RESET_DATE = '2026-11-12'
COMPARE_COLUMNS = ('ml_modele_statut','top3_direct_rang','top3_direct_score','top3_direct_top3','top3_direct_statut','top3_cotes_valeur','top3_cotes_top3','top3_cotes_statut','ml_score_non_calibre','top3_direct_utc','top3_cotes_utc','ml_rang','ml_top3','ml_proba_podium','arrivee_rang','meteo_resume','meteo_statut')
REPORT_COLUMNS = ('top3_direct_numeros','score_direct','top3_cotes_numeros','score_cotes','top3_ml_numeros','analyse_comparative','score_baseline','score_baseline_final','score_ml','etat_ml',
                  'source_export','derniere_sync_utc')
HIST_MAPPING = {'identifiant_cheval':'cheval_id','cheval':'nom','date_course_historique':'date',
                'hippodrome':'hippodrome','discipline':'discipline','distance_m':'distance_m',
                'classement':'classement','chrono':'chrono','source_url':'texte_source'}


# Les libelles Google Sheets sont independants des noms techniques Python.
# Une seule correspondance stable permet de conserver la synchronisation idempotente.
DISPLAY_NAMES = {
    'course_key':'Clé course (technique)',
    'date_course':'Date',
    'hippodrome':'Hippodrome',
    'rncn':'Course R/C',
    'heure_depart_paris':'Départ (Paris)',
    'discipline':'Discipline',
    'distance_m':'Distance (m)',
    'numero':'N°',
    'cheval':'Cheval',
    'top3_direct_rang':'TOP3 direct · Rang',
    'top3_direct_score':'TOP3 direct · Score',
    'top3_direct_top3':'TOP3 direct · Sélection',
    'top3_direct_statut':'TOP3 direct · Couverture',
    'driver_jockey':'Driver / Jockey',
    'entraineur':'Entraîneur',
    'proprietaire':'Propriétaire',
    'ferrure':'Ferrure',
    'non_partant':'Non-partant (NP)',
    'historique_statut':'Historique · État',
    'historique_nb_courses_datees':'Historique · Nb performances récupérées',
    'historique_maj_utc':'Historique · Mise à jour UTC',
    'actuel_statut':'PMU · Complétude fiche',
    'actuel_maj_utc':'Données actuelles · Mise à jour UTC',
    'statut_prevision':'Prévisions · État',
    'avis_pmu':'Avis expert PMU',
    'avis_geny':'Avis expert Geny',
    'avis_zone_turf':'Avis expert Zone-Turf',
    'synthese_actualite':'Synthèse des avis',
    'ml_modele_statut':'ML · État du modèle',
    'ml_rang':'ML · Rang',
    'ml_top3':'ML · Sélection',
    'ml_proba_podium':'ML · Probabilité calibrée',
    'ml_score_non_calibre':'ML · Score non calibré',
    'top3_cotes_valeur':'Cotes · Valeur',
    'top3_cotes_top3':'Cotes · Sélection',
    'top3_cotes_statut':'Cotes · État',
    'top3_direct_utc':'TOP3 direct · Calcul UTC',
    'top3_cotes_utc':'TOP3 cotes · Calcul UTC',
    'arrivee_rang':'Arrivée · Rang officiel',
    'meteo_resume':'Météo · Synthèse',
    'meteo_statut':'Météo · État',
}
INVERSE_NAMES = {label:key for key,label in DISPLAY_NAMES.items()}
assert len(INVERSE_NAMES)==len(DISPLAY_NAMES)

def canonical_headers(visible):
    return [INVERSE_NAMES.get(name,name) for name in visible]


def read_csv(path):
    with open(path,encoding='utf-8-sig',newline='') as f:
        return list(csv.DictReader(f,delimiter=';'))


def load_json(path):
    try: return json.loads(path.read_text(encoding='utf-8'))
    except (OSError,ValueError): return {}


def colname(n):
    s=''
    while n:
        n,r=divmod(n-1,26);s=chr(65+r)+s
    return s


def course_info(cache,code,date):
    data=load_json(cache/'sources_pmu'/f'programme_{date}.json')
    for x in data.get('programme',[]):
        if x.get('code')==code:return x
    return {}


def course_key(date,hippodrome,code):
    hip=str(hippodrome).strip().upper()
    for prefix in ('HIPPODROME DE PARIS-', 'HIPPODROME DE ', "HIPPODROME D'", 'HIPPODROME DU ', 'HIPPODROME DES '):
        if hip.startswith(prefix):hip=hip[len(prefix):];break
    return '|'.join([date,hip,code])


def source_rows(cache):
    courses, history, reports = {}, {}, {}
    import unicodedata
    def normalize_horse_name(value):
        s=unicodedata.normalize('NFKD',str(value or '').casefold())
        return ''.join(c for c in s if c.isalnum() and not unicodedata.combining(c))
    status=load_json(cache/'etat_persistant.json').get('chevaux',{})
    known={}
    for ident,item in status.items():
        if item.get('statut')!='COMPLET':continue
        doc=load_json(cache/'historiques'/str(ident)/'historique_geny.json')
        if doc.get('statut')!='COMPLET' or not isinstance(doc.get('performances'),list):continue
        key=normalize_horse_name(item.get('nom'))
        if key:known.setdefault(key,[]).append((ident,len(doc['performances']),item.get('maj_utc','')))

    for path in sorted((cache/'exports').glob('GENY-*/comparatif_predictions.csv')):
        try: comparisons=read_csv(path)
        except (OSError,ValueError):continue
        for r in comparisons:
            date=r.get('date','');code=r.get('course','');n=r.get('numero','')
            if not date or not code or not n:continue
            info=course_info(cache,code,date)
            if not info:continue
            hip=info.get('hippodrome','')
            k=course_key(date,hip,code);row_key=f'{k}|{n}'
            cid=path.parent.name
            manifest=load_json(cache/'manifestes'/f'{cid}.json')
            horses=(manifest.get('courses') or [{}])[0].get('partants',[])
            horse=next((h for h in horses if str(h.get('numero'))==str(n)),{})
            participant=load_json(cache/'partants_actuels'/f'{date}_{code}.json')
            actual=(participant.get('chevaux') or {}).get(str(n),{})
            suivi_path=cache/'exports'/cid/'suivi_chevaux.csv'
            try: suivi=read_csv(suivi_path)
            except (OSError,ValueError):suivi=[]
            historique=next((h for h in suivi if str(h.get('numero'))==str(n)),{})
            frozen=load_json(cache/'pronostics'/f'{date}_{code}_top3.json')
            latest=load_json(cache/'pronostics'/f'{date}_{code}_baseline_latest.json')
            ml=load_json(cache/'pronostics'/f'{date}_{code}_ml_latest.json')
            depart=str(r.get('depart',''))
            official=load_json(cache/'arrivees'/f'{date}_{code}.json')
            has_historical=bool(frozen.get('top3'))
            has_ml=bool(ml.get('top3'))
            forecast_state=('FIGE_HISTORIQUE' if has_historical else
                            'ML_SEUL_DISPONIBLE' if has_ml else 'TOP3_NON_FIGE')
            doc={'course_key':k,'date_course':date,'hippodrome':hip,'rncn':code,
                 'heure_depart_paris':depart,'discipline':info.get('discipline',''),
                 'distance_m':info.get('distance_m',''),'numero':n,'cheval':r.get('nom',''),
                 'driver_jockey':actual.get('driver_jockey','') or horse.get('driver_jockey',''),
                 'entraineur':actual.get('entraineur','') or horse.get('entraineur',''),
                 'proprietaire':actual.get('proprietaire','') or horse.get('proprietaire',''),
                 'ferrure':actual.get('ferrure','') or horse.get('ferrure',''),
                 'non_partant':r.get('statut_np',''),
                 'historique_statut':historique.get('historique_statut',''),
                 'historique_nb_courses_datees':historique.get('nombre_performances_persistantes',''),
                 'historique_maj_utc':historique.get('historique_maj_utc',''),
                 'actuel_statut':('PMU_FERRURE_DISPONIBLE' if (actual or {}).get('ferrure') else 'PMU_FERRURE_NON_RECUPEREE') if actual else 'PMU_PARTANTS_NON_RECUPERES',
                 'actuel_maj_utc':participant.get('capture_utc',''),
                 'statut_prevision':forecast_state,
                 'fige_utc':frozen.get('frozen_at',''),
                 'mode_calcul_top3':'BASELINE_HISTORIQUE' if has_historical else ('ML' if has_ml else 'NON_CALCULE'),
                 'historique_modele_statut':'FIGE' if has_historical else 'NON_CALCULE',
                 'ml_modele_statut':ml.get('statut','ML_NON_ENTRAINE'),
                 'secours_statut':'NON_CALCULE',
                 'rang_top3':r.get('baseline_final_rang','') if r.get('baseline_final_top3')=='OUI' else ''}
            for c in COMPARE_COLUMNS:
                if c not in doc:doc[c]=r.get(c,'')
            # Un score brut ML n'est pas une probabilite calibree.
            if ml.get('statut')!='ML_ENTRAINE_CALIBRE':
                doc['ml_score_non_calibre']=r.get('ml_proba_podium','')
                doc['ml_proba_podium']=''
            courses[row_key]=doc
            if official.get('arrivee'):
                positions=[str(x.get('numero')) for x in sorted(official['arrivee'],key=lambda x:x.get('rang',999)) if x.get('rang') in (1,2,3)]
                if len(positions)!=3:continue
                comparison_present=bool(has_historical or has_ml)
                reports[k]={'course_key':k,'date_course':date,'hippodrome':hip,'rncn':code,
                            'heure_depart_paris':depart,
                            'top3_prevu_numeros':','.join(str(x.get('numero')) for x in (latest or frozen).get('top3',[])) if has_historical else '',
                            'fige_utc':frozen.get('frozen_at',''),
                            'arrivee_officielle_numeros':','.join(positions),
                            'source_arrivee_url':'PMU_API_PARTICIPANTS',
                            'arrivee_verifiee_utc':official.get('verifie_utc',''),
                            'score_baseline':r.get('baseline_hits_course',''),
                            'score_baseline_final':r.get('baseline_final_hits_course',''),
                            'score_ml':r.get('ml_hits_course',''),
                            'score_sur_3':r.get('baseline_final_hits_course','') if has_historical else '',
                            'etat_ml':ml.get('statut','ML_NON_ENTRAINE'),
                            'source_export':str(path.relative_to(cache)),
                            'derniere_sync_utc':datetime.now(timezone.utc).isoformat(),
                            'statut_evaluation':'EVALUE' if comparison_present and r.get('baseline_final_hits_course') else 'ARRIVEE_SANS_TOP3_FIGE'}
    # PMU seul : creer la fiche de chaque partant meme sans manifeste/historique Geny.
    # Les trois paliers sont independants; aucun score n'est invente.
    for participant_file in sorted((cache/'partants_actuels').glob('????-??-??_R*C*.json')):
        match=re.fullmatch(r'(\d{4}-\d{2}-\d{2})_(R\d+C\d+)\.json',participant_file.name)
        if not match:continue
        date,code=match.groups()
        info=course_info(cache,code,date)
        if not info:continue
        participant=load_json(participant_file)
        direct=load_json(cache/'pronostics'/f'{date}_{code}_direct.json')
        marche=load_json(cache/'pronostics'/f'{date}_{code}_cotes.json')
        cotes_source=load_json(cache/'cotes'/f'{date}_{code}.json')
        cotes_etat=marche.get('statut') or cotes_source.get('statut') or (
            'COTES_NON_EXTRAITES' if cotes_source.get('chevaux') and not any(
                h.get('cote') is not None for h in cotes_source['chevaux']) else 'PAS_DE_RELEVE')
        ml=load_json(cache/'pronostics'/f'{date}_{code}_ml_latest.json')
        contexte=load_json(cache/'contextes'/f'{date}_{code}.json')
        observations={x.get('champ'):x.get('valeur') for x in contexte.get('observations',[])
                      if isinstance(x,dict) and x.get('champ','').startswith('meteo_')}
        meteo_resume=''
        if observations:
            parts=[]
            for champ,unite in (('meteo_temperature_c','°C'),
                                ('meteo_pluie_mm','mm pluie'),
                                ('meteo_vent_kmh','km/h vent'),
                                ('meteo_humidite_pct','% humidité')):
                if observations.get(champ) is not None:
                    parts.append(f"{observations[champ]:g} {unite}" if isinstance(observations[champ],(int,float))
                                 else f"{observations[champ]} {unite}")
            meteo_resume=' · '.join(parts)
        meteo_statut=contexte.get('meteo_statut') if meteo_resume else 'METEO_NON_RECUPEREE'
        hip=info.get('hippodrome','')
        k=course_key(date,hip,code)
        ranks={}
        for mode,document in (('direct',direct),('cotes',marche),('ml',ml)):
            ranks[mode]={str(h.get('numero')):(i,h) for i,h in
                         enumerate(document.get('classement_complet',[]),start=1)}
        from .liaison_chevaux_v22 import etablir
        liens=etablir(cache,{'date':date,'code':code},[
            {'numero':n,'nom':v.get('nom','')}
            for n,v in (participant.get('chevaux') or {}).items()
        ])
        for n,act in (participant.get('chevaux') or {}).items():
            krow=f'{k}|{n}'
            existing=courses.get(krow,{})
            direct_rank,direct_h=ranks['direct'].get(str(n),('',{}))
            cote_rank,cote_h=ranks['cotes'].get(str(n),('',{}))
            ml_rank,ml_h=ranks['ml'].get(str(n),('',{}))
            link=liens.get(str(n),{})
            link_method=link.get('methode','NON_ASSOCIE')
            hist=link.get('historique',{})
            hist_status=(
                'HISTO_OK_ID' if link_method=='ID_GENY_MANIFESTE_VERIFIE'
                else 'HISTO_OK_NOM' if link_method=='NOM_EXACT_UNIQUE'
                else 'HISTO_AMBIGU' if link_method=='NOM_AMBIGU'
                else 'HISTO_NON_COLLECTE')
            current={
                'meteo_resume':meteo_resume,
                'meteo_statut':meteo_statut,
                'historique_statut':hist_status,
                'historique_nb_courses_datees':len(hist.get('performances',[])) if hist else '',
                'historique_maj_utc':status.get(link.get('cheval_id'),{}).get('maj_utc','') if hist else '',
                'course_key':k,'date_course':date,'hippodrome':hip,'rncn':code,
                'heure_depart_paris':info.get('depart',''),
                'discipline':info.get('discipline',''),
                'distance_m':info.get('distance_m',''),
                'numero':str(n),'cheval':act.get('nom','') or existing.get('cheval',''),
                'driver_jockey':act.get('driver_jockey',''),
                'entraineur':act.get('entraineur',''),
                'proprietaire':act.get('proprietaire',''),
                'ferrure':act.get('ferrure',''),
                'non_partant':act.get('statut_np','NP_NON_VERIFIE'),
                'actuel_statut':('PMU_FERRURE_DISPONIBLE' if act.get('ferrure') else 'PMU_FERRURE_NON_RECUPEREE') if act else 'PMU_PARTANTS_NON_RECUPERES',
                'actuel_maj_utc':participant.get('capture_utc',''),
                'top3_direct_rang':direct_rank,
                'top3_direct_score':direct_h.get('score_direct',''),
                'top3_direct_top3':'OUI' if direct_rank and direct_rank<=3 else '',
                'top3_direct_statut':direct.get('statut','NON_CALCULE'),
                'top3_cotes_valeur':cote_h.get('cote',''),
                'top3_cotes_top3':'OUI' if cote_rank and cote_rank<=3 else '',
                'top3_cotes_statut':cotes_etat,
                'ml_rang':ml_rank,
                'ml_score_non_calibre':ml_h.get('proba_podium_estimee',''),
                'ml_top3':'OUI' if ml_rank and ml_rank<=3 else '',
                'ml_modele_statut':ml.get('statut','ML_NON_ENTRAINE'),
                'statut_prevision':'PREVISIONS_DISPONIBLES' if direct_rank or cote_rank or ml_rank else existing.get('statut_prevision','TOP3_NON_CALCULE'),
                'mode_calcul_top3':'DIRECT+COTES+ML_SEPARES' if direct_rank or cote_rank or ml_rank else existing.get('mode_calcul_top3','NON_CALCULE'),
                'top3_direct_utc':direct.get('calcul_utc',''),
                'top3_cotes_utc':marche.get('calcul_utc',''),
                'version_ml_utc':ml.get('calcul_utc',''),
            }
            # Conserver les informations Geny si deja plus riches et presentes.
            courses[krow]={**existing,**{key:value for key,value in current.items()
                                         if value is not None and value!=''}}
    # Les arrivees PMU officielles peuvent exister sans manifeste Geny.
    # Enregistrer une ligne bilan par course meme sans TOP3.
    for arrival_file in sorted((cache/'arrivees').glob('????-??-??_R*C*.json')):
        match=re.fullmatch(r'(\d{4}-\d{2}-\d{2})_(R\d+C\d+)\.json',arrival_file.name)
        if not match:continue
        date,code=match.groups()
        info=course_info(cache,code,date)
        if not info:continue
        arrivee=load_json(arrival_file)
        podium=sorted(
            (x for x in arrivee.get('arrivee',[]) if x.get('rang') in (1,2,3)),
            key=lambda x:x['rang'])
        if len(podium)!=3 or [x['rang'] for x in podium]!=[1,2,3]:continue
        k=course_key(date,info.get('hippodrome',''),code)
        existing=reports.get(k,{})
        forecast=load_json(cache/'pronostics'/f'{date}_{code}_top3.json')
        latest=load_json(cache/'pronostics'/f'{date}_{code}_baseline_latest.json')
        predicted=(latest or forecast).get('top3',[])
        nums=[str(x['numero']) for x in predicted]
        scores=len(set(nums)&{str(x['numero']) for x in podium}) if len(nums)==3 else ''
        direct=load_json(cache/'pronostics'/f'{date}_{code}_direct.json')
        marche=load_json(cache/'pronostics'/f'{date}_{code}_cotes.json')
        ml=load_json(cache/'pronostics'/f'{date}_{code}_ml_latest.json')
        def _eval_podium(doc):
            nums=[str(x['numero']) for x in doc.get('top3',[])]
            return (','.join(nums),len(set(nums)&{str(x['numero']) for x in podium})) if len(nums)==3 else ('','')
        direct_nums,direct_hits=_eval_podium(direct)
        cote_nums,cote_hits=_eval_podium(marche)
        ml_nums,ml_hits=_eval_podium(ml)
        reports[k]={**existing,
                    'top3_direct_numeros':direct_nums,'score_direct':direct_hits,
                    'top3_cotes_numeros':cote_nums,'score_cotes':cote_hits,
                    'top3_ml_numeros':ml_nums,'score_ml':ml_hits,
                    'analyse_comparative':('DIRECT='+str(direct_hits)+'; COTES='+str(cote_hits)+'; ML='+str(ml_hits)),
                    'course_key':k,'date_course':date,'hippodrome':info.get('hippodrome',''),
                    'rncn':code,'heure_depart_paris':info.get('depart',''),
                    'top3_prevu_numeros':','.join(nums),
                    'fige_utc':forecast.get('frozen_at',''),
                    'arrivee_officielle_numeros':','.join(str(x['numero']) for x in podium),
                    'source_arrivee_url':arrivee.get('source','PMU_API_PARTICIPANTS'),
                    'arrivee_verifiee_utc':arrivee.get('verifie_utc',''),
                    'score_sur_3':scores,
                    'statut_evaluation':'EVALUE' if any(x!='' for x in (scores,direct_hits,cote_hits,ml_hits)) else 'ARRIVEE_SANS_TOP3_FIGE'}
    # V21: une cle (cheval, date, hippodrome) ne suffit pas:
    # un cheval peut courir deux fois le meme jour au meme hippodrome.
    # Dedoublonner entre exports de courses, mais jamais deux lignes source
    # distinctes. Conserver la cle historique pour la premiere performance
    # afin de ne pas recreer toutes les lignes existantes dans Google Sheets.
    grouped={}
    for path in sorted((cache/'exports').glob('GENY-*/performances.csv')):
        try: perfs=read_csv(path)
        except (OSError,ValueError):continue
        for r in perfs:
            ident=r.get('cheval_id','');date=r.get('date','');hip=r.get('hippodrome','')
            if not ident or not date:continue
            base=f'{ident}|{date}|{hip.strip().upper()}'
            source=' '.join(str(r.get('texte_source','')).split())
            # Un texte source vide ne prouve pas une seconde performance.
            signature=source or '|'.join(str(r.get(k,'')) for k in (
                'discipline','distance_m','classement','chrono'))
            grouped.setdefault(base,{}).setdefault(signature,r)
    # Source canonique V22 : historiques persistants independants des exports
    # de course. Sans ce passage, les historiques importes sont invisibles dans Sheets.
    journal=load_json(cache/'etat_persistant.json').get('chevaux',{})
    for file in sorted((cache/'historiques').glob('*/historique_geny.json')):
        ident=file.parent.name
        doc=load_json(file)
        if doc.get('statut')!='COMPLET' or not isinstance(doc.get('performances'),list):
            continue
        cheval=journal.get(ident,{}).get('nom','')
        for perf in doc['performances']:
            date=perf.get('date','')
            hip=str(perf.get('hippodrome','')).strip()
            if not date or not hip:continue
            source=' '.join(str(perf.get('texte_source','')).split())
            signature=source or '|'.join(str(perf.get(k,'')) for k in (
                'discipline','distance_m','classement','chrono'))
            base=f'{ident}|{date}|{hip.upper()}'
            row={'cheval_id':ident,'nom':cheval,**perf}
            grouped.setdefault(base,{}).setdefault(signature,row)
    for base, variants in grouped.items():
        for n,(signature,r) in enumerate(sorted(variants.items()),start=1):
            if n==1:
                k=base
            else:
                suffix=hashlib.sha256(signature.encode('utf-8')).hexdigest()[:16]
                k=f'{base}|{suffix}'
            doc={out:r.get(inn,'') for out,inn in HIST_MAPPING.items()}
            doc['cle_performance']=k
            doc['statut_verification']='EXTRACTION_GENY'
            history[k]=doc
    return {'Courses & Prévisions':courses,'Historique chevaux':history,'Résultats & Analyse':reports}


def ensure_headers(existing, additions):
    return existing + [x for x in additions if x not in existing]


def plan_sheet(existing_headers,existing_rows,new_items,tab,now=None):
    """Planning sans mutation: met à jour uniquement les colonnes propriétaires du bridge."""
    keys={'Courses & Prévisions':('course_key','numero'),
          'Historique chevaux':('cle_performance',),
          'Résultats & Analyse':('course_key',)}[tab]
    additions=COMPARE_COLUMNS if tab=='Courses & Prévisions' else REPORT_COLUMNS if tab=='Résultats & Analyse' else ()
    headers=ensure_headers(existing_headers,tuple(additions))
    if not all(x in headers for x in keys):raise ValueError(f'Colonnes cle manquantes pour {tab}: {keys}')
    def rowkey(row):return '|'.join(str(row.get(x,'')).strip() for x in keys)
    present={rowkey(r):idx+2 for idx,r in enumerate(existing_rows) if all(str(r.get(k,'')).strip() for k in keys)}
    changes=[];append=[]
    for item in new_items.values():
        k=rowkey(item)
        if k in present:
            # writes only values actually present/nonempty; leaves other cells untouched.
            for name,val in item.items():
                if (name in headers and val is not None and str(val)!=''
                        and str(existing_rows[present[k]-2].get(name,'')) != str(val)):
                    changes.append((present[k],headers.index(name)+1,str(val)))
        else:
            append.append([str(item.get(h,'')) if item.get(h) is not None else '' for h in headers]);present[k]=-1
    return headers,changes,append


def limiter_cours_registre(source, date_debut=LIVE_RESET_DATE):
    """Ne filtre que les onglets operationnels; ne touche jamais aux historiques."""
    result=dict(source)
    for onglet in ('Courses & Prévisions', 'Résultats & Analyse'):
        result[onglet]={key:row for key,row in source[onglet].items()
                        if str(row.get('date_course',''))>=date_debut}
    return result


def main():
    cache=Path(os.getenv('PMU_CACHE','cache_pmu'))
    spreadsheet=os.getenv('GOOGLE_SHEETS_ID','1BjzDzC6NsLRMax2XjrCIcCIIgz6hyCJ1YTWOa5hiGLo')
    secret=os.getenv('GOOGLE_SHEETS_SERVICE_ACCOUNT_JSON','')
    if not secret:
        print('SYNC_GOOGLE_SHEETS=NON_CONFIGURE: secret absent');return 0
    try:
        import google.oauth2.service_account
        from google.auth.transport.requests import AuthorizedSession
        info=json.loads(secret)
        creds=google.oauth2.service_account.Credentials.from_service_account_info(
            info,scopes=['https://www.googleapis.com/auth/spreadsheets'])
        session=AuthorizedSession(creds)
    except (ImportError,ValueError,KeyError,TypeError) as exc:
        print(f'SYNC_GOOGLE_SHEETS=ERREUR_IDENTIFIANTS {type(exc).__name__}');return 2
    base=f'https://sheets.googleapis.com/v4/spreadsheets/{spreadsheet}'
    source=limiter_cours_registre(source_rows(cache))
    print(f'REGISTRE_DEBUT_PRODUCTION={LIVE_RESET_DATE}; anciennes courses conservees hors Sheets')
    metadata=session.get(base,params={'fields':'sheets(properties(sheetId,title,gridProperties(columnCount)))'},timeout=30)
    if metadata.status_code != 200:
        print(f'SYNC_GOOGLE_SHEETS=ERREUR_META http={metadata.status_code}')
        return 2
    by_name={x['properties']['title']:x['properties'] for x in metadata.json().get('sheets',[])}
    errors=0
    for tab in SHEET_TABS:
        import urllib.parse
        quoted=urllib.parse.quote("'"+tab.replace("'","''")+"'!A1:BS5000",safe='!:\'')
        response=session.get(f'{base}/values/{quoted}',timeout=30)
        if response.status_code!=200:
            print(f'SYNC_GOOGLE_SHEETS=ERREUR_LECTURE onglet={tab} http={response.status_code}');errors+=1;continue
        values=response.json().get('values',[])
        headers=canonical_headers(values[0] if values else [])
        existing=[dict(zip(headers,row)) for row in values[1:]]
        try: all_headers,updates,appends=plan_sheet(headers,existing,source[tab],tab)
        except ValueError as exc:print('SYNC_GOOGLE_SHEETS=SCHEMA_INCOMPATIBLE',str(exc));errors+=1;continue
        updates_cells=[]
        # Only write bridge-owned fields of existing rows (the user retains all other cells).
        extra=all_headers[len(headers):]
        # Dimensionner la grille avant toute écriture hors limite actuelle.
        properties=by_name.get(tab)
        if properties is None:
            print(f'SYNC_GOOGLE_SHEETS=ONGLET_ABSENT {tab}');errors+=1;continue
        current_width=properties.get('gridProperties',{}).get('columnCount',0)
        if len(all_headers)>current_width:
            grow={'requests':[{'appendDimension':{'sheetId':properties['sheetId'],
                  'dimension':'COLUMNS','length':len(all_headers)-current_width}}]}
            response=session.post(base+':batchUpdate',json=grow,timeout=30)
            if response.status_code!=200:
                print(f'SYNC_GOOGLE_SHEETS=ERREUR_COLONNES onglet={tab} http={response.status_code}')
                errors+=1;continue
        if extra:
            updates_cells.append({'range':f"'{tab}'!{colname(len(headers)+1)}1:{colname(len(all_headers))}1",'values':[[DISPLAY_NAMES.get(k,k) for k in extra]]})
        for r,c,v in updates:
            updates_cells.append({'range':f"'{tab}'!{colname(c)}{r}",'values':[[v]]})
        # Use a single batchUpdate per tab, plus append for new rows.
        for offset in range(0,len(updates_cells),350):
            chunk=updates_cells[offset:offset+350]
            res=session.post(f'{base}/values:batchUpdate',json={'valueInputOption':'RAW','data':chunk},timeout=45)
            if res.status_code!=200:
                print(f'SYNC_GOOGLE_SHEETS=ERREUR_MAJ onglet={tab} http={res.status_code}');errors+=1;break
        if appends:
            url=f'{base}/values/'+urllib.parse.quote("'"+tab+"'!A1",safe='!:\'')+':append'
            res=session.post(url,params={'valueInputOption':'RAW','insertDataOption':'INSERT_ROWS'},
                             json={'values':appends},timeout=45)
            if res.status_code!=200:
                print(f'SYNC_GOOGLE_SHEETS=ERREUR_AJOUT onglet={tab} http={res.status_code}');errors+=1
        print(f'SYNC_GOOGLE_SHEETS onglet={tab} lignes_source={len(source[tab])} '
              f'cellules_mises_a_jour={len(updates)} lignes_ajoutees={len(appends)}')
    return 1 if errors else 0

if __name__=='__main__':sys.exit(main())
