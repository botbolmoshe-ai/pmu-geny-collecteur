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

from dashboard.trot_analytics.dates import date_kind, depuis_nombre, instant_iso, meme_date_sheets

SHEET_TABS = ('Courses & Prévisions', 'Historique chevaux', 'Résultats & Analyse')
# Nouvelle base visuelle : ne pas republier les anciennes courses apres le nettoyage.
# Les fichiers bruts, les audits et tous les historiques sont conserves dans pmu-data.
LIVE_RESET_DATE = '2026-11-12'
RETIRED_EXPERT_COLUMNS = frozenset({'avis_equidia','avis_zeturf','prono_equidia','prono_zeturf',
                                   'source_equidia','source_zeturf'})
RETIRED_SHEET_COLUMNS = {
    'Courses & Prévisions':RETIRED_EXPERT_COLUMNS | frozenset({
        'ml_proba_podium','synthese_actualite','divergences_sources'}),
    'Historique chevaux':frozenset({'rncn','nombre_partants','gains_course_eur',
        'driver_jockey','entraineur','date_source'}),
    'Résultats & Analyse':frozenset({'top3_cotes_numeros','score_cotes',
        'analyse_comparative','derniere_sync_utc'}),
}
SHEET_HEADER_LABELS = {
    'Courses & Prévisions':{'actuel_statut':'PMU · État ferrure',
        'couverture_experts':'PMU · Disponibilité avis/pronostic'},
    'Historique chevaux':{'extraction_utc':'Capture historique · UTC'},
}
EDITORIAL_COLUMNS = ('avis_24h_trot', 'source_24h_trot')
EXPERT_COLUMNS = ('avis_pmu','prono_pmu','source_pmu','couverture_experts',
                  'conditions_course','age_ans','sexe','gains_euros')
PROFILE_COLUMNS = ('profil_partant', 'profil_partant_indices')
COURSE_PMU_COLUMNS = ('course_nom_pmu', 'course_categorie_pmu', 'course_ages_admis',
                      'course_allocation_eur', 'course_parcours', 'course_mode_depart')
REPORT_NAME_COLUMNS = {'top3_direct_numeros': 'top3_direct_noms',
                       'top3_ml_numeros': 'top3_ml_noms',
                       'arrivee_officielle_numeros': 'arrivee_officielle_noms'}
DEPART_COLUMNS = ('position_autostart', 'ligne_autostart', 'capacite_autostart', 'recul_depart_m')
WINNER_SELECTION_COLUMNS = ('gagnant_direct_selection', 'gagnant_ml_selection')
WINNER_REPORT_COLUMNS = tuple(
    f'gagnant_{mode}_{field}'
    for mode in ('direct', 'ml')
    for field in ('numero', 'nom', 'rang', 'verdict')
)
COTES_COLUMNS = ('top3_cotes_valeur', 'cote_releve_utc', 'cote_rapport_utc',
                 'top3_cotes_top3', 'top3_cotes_rang', 'top3_cotes_statut', 'top3_cotes_utc')
COMPARE_COLUMNS = PROFILE_COLUMNS + EXPERT_COLUMNS + EDITORIAL_COLUMNS + ('ml_modele_statut','top3_direct_rang','top3_direct_score','top3_direct_top3','top3_direct_statut','ml_score_non_calibre','top3_direct_utc','version_ml_utc','ml_rang','ml_top3','arrivee_rang','meteo_resume','meteo_statut') + COURSE_PMU_COLUMNS + WINNER_SELECTION_COLUMNS + COTES_COLUMNS + DEPART_COLUMNS
RAPPROCHEMENT_COLUMNS = ('reunion_pmu', 'rapprochement_statut', 'rapprochement_arrivee_statut',
                         'rapprochement_declenchement_utc') + tuple(
    f'score_{phase}_{kind}' for phase in ('h2', 'h1') for kind in ('direct', 'ml'))
REPORT_COLUMNS = ('course_key','date_course','hippodrome','rncn','heure_depart_paris',
                  'top3_direct_numeros','top3_direct_noms','top3_direct_calcule_utc','score_direct',
                  'top3_ml_numeros','top3_ml_noms','score_ml','etat_ml',
                  'arrivee_officielle_numeros','arrivee_officielle_noms','arrivee_verifiee_utc',
                  'statut_evaluation','conclusion','matching_direct_pct','matching_ml_pct') + WINNER_REPORT_COLUMNS + RAPPROCHEMENT_COLUMNS
NUMERIC_SCORES = frozenset({'score_direct','score_cotes','score_ml','score_sur_3',
                            'score_baseline','score_baseline_final', *RAPPROCHEMENT_COLUMNS[4:]})
MATCHING_COLUMNS = frozenset({'matching_direct_pct','matching_ml_pct'})
CLEARABLE_COLUMNS = frozenset(PROFILE_COLUMNS + DEPART_COLUMNS) | MATCHING_COLUMNS | frozenset(EXPERT_COLUMNS) | frozenset({
    *RETIRED_EXPERT_COLUMNS,  # Lecture/nettoyage des anciens formats uniquement.
    'top3_direct_rang','top3_direct_score','top3_direct_top3',
    *COTES_COLUMNS,'ml_rang','ml_top3',
    'ml_proba_podium','ml_score_non_calibre',
    'top3_direct_source_forme','top3_direct_qualite','top3_direct_historiques_exploites',
    *REPORT_NAME_COLUMNS.values(), *WINNER_SELECTION_COLUMNS, *WINNER_REPORT_COLUMNS})
PARTANT_PMU_COLUMNS = frozenset({'driver_jockey','entraineur','proprietaire','ferrure','musique_pmu'})

def sheet_value(field, value):
    if value is None:return ''
    if field == 'top3_cotes_valeur':
        from .cotes_v19 import cote_valide
        return cote_valide(value) or ''
    if field == 'course_allocation_eur':
        return value if type(value) is int and value > 0 else ''
    if field in MATCHING_COLUMNS:
        return value if isinstance(value,(int,float)) and not isinstance(value,bool) and 0<=value<=100 else ''
    if field in NUMERIC_SCORES and str(value) in ('0','1','2','3'):
        return int(value)
    return str(value)
HIST_MAPPING = {'identifiant_cheval':'cheval_id','cheval':'nom','date_course_historique':'date',
                'hippodrome':'hippodrome','discipline':'discipline','distance_m':'distance_m',
                'classement':'classement','chrono':'chrono','source_url':'texte_source',
                'ferrure':'ferrure','extraction_utc':'_capture_historique_utc'}


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
    'profil_partant':'Profil du cheval',
    'profil_partant_indices':'Profil · Indices',
    'top3_direct_rang':'TOP3 direct · Rang',
    'top3_direct_score':'TOP3 direct · Score',
    'top3_direct_top3':'TOP3 direct · Sélection',
    'top3_direct_statut':'TOP3 direct · Couverture',
    'top3_direct_source_forme':'TOP3 direct · Source de forme',
    'top3_direct_qualite':'TOP3 direct · Qualité du contexte',
    'top3_direct_historiques_exploites':'TOP3 direct · Performances comparées',
    'musique_pmu':'Musique PMU',
    'driver_jockey':'Driver / Jockey',
    'entraineur':'Entraîneur',
    'proprietaire':'Propriétaire',
    'ferrure':'Ferrure · Course du jour',
    'top3_direct_numeros':'TOP3 direct · Chevaux',
    'top3_direct_noms':'TOP3 direct · Noms',
    'top3_direct_calcule_utc':'TOP3 direct · Heure calcul UTC',
    'score_direct':'TOP3 direct · Chevaux à l’arrivée (0–3)',
    'top3_cotes_numeros':'TOP3 cotes · Chevaux',
    'score_cotes':'TOP3 cotes · Chevaux à l’arrivée (0–3)',
    'top3_ml_numeros':'TOP3 ML · Chevaux',
    'top3_ml_noms':'TOP3 ML · Noms',
    'score_ml':'TOP3 ML · Chevaux à l’arrivée (0–3)',
    'matching_direct_pct':'TOP3 direct · Matching (%)',
    'matching_ml_pct':'TOP3 ML · Matching (%)',
    'gagnant_direct_selection':'Gagnant potentiel direct · Sélection',
    'gagnant_ml_selection':'Gagnant potentiel ML · Sélection',
    'gagnant_direct_numero':'Gagnant potentiel direct · N°',
    'gagnant_direct_nom':'Gagnant potentiel direct · Nom',
    'gagnant_direct_rang':'Gagnant potentiel direct · Rang officiel',
    'gagnant_direct_verdict':'Gagnant potentiel direct · Verdict',
    'gagnant_ml_numero':'Gagnant potentiel ML · N°',
    'gagnant_ml_nom':'Gagnant potentiel ML · Nom',
    'gagnant_ml_rang':'Gagnant potentiel ML · Rang officiel',
    'gagnant_ml_verdict':'Gagnant potentiel ML · Verdict',
    'etat_ml':'ML · Statut',
    'arrivee_officielle_numeros':'Arrivée · N° officiels',
    'arrivee_officielle_noms':'Arrivée · Noms officiels',
    'arrivee_verifiee_utc':'Arrivée · Vérifiée UTC',
    'statut_evaluation':'Évaluation · État',
    'analyse_comparative':'Évaluation · Comparatif 3 méthodes',
    'conclusion':'Évaluation · Conclusion',
    'derniere_sync_utc':'Dernière synchronisation UTC',

    'age_ans':'Âge (ans)',
    'sexe':'Sexe',
    'gains_euros':'Gains carrière (€)',
    'non_partant':'Non-partant (NP)',
    'historique_statut':'Historique · État',
    'historique_nb_courses_datees':'Historique · Nb performances récupérées',
    'historique_maj_utc':'Historique · Mise à jour UTC',
    'actuel_statut':'PMU · État ferrure',
    'actuel_maj_utc':'Données actuelles · Mise à jour UTC',
    'statut_prevision':'Prévisions · État',
    'avis_24h_trot':'24H au Trot · Article avant course',
    'source_24h_trot':'24H au Trot · Source et lecture UTC',
    'avis_pmu':'Avis expert PMU',
    'avis_equidia':'Avis expert Equidia',
    'avis_zeturf':'Avis expert ZEturf',
    'prono_pmu':'Pronostic PMU · Ordre publié',
    'prono_equidia':'Pronostic Equidia · Ordre publié',
    'prono_zeturf':'Pronostic ZEturf · Ordre publié',
    'source_pmu':'Source PMU · URL et collecte UTC',
    'source_equidia':'Source Equidia · URL et collecte UTC',
    'source_zeturf':'Source ZEturf · URL et collecte UTC',
    'couverture_experts':'PMU · Disponibilité avis/pronostic',
    'divergences_sources':'Sources · Divergences / avis identiques',
    'conditions_course':'Conditions de course',
    'course_nom_pmu':'Course · Nom PMU',
    'course_categorie_pmu':'Course · Catégorie PMU',
    'course_ages_admis':'Course · Âges admis',
    'course_allocation_eur':'Course · Allocation (€)',
    'course_parcours':'Course · Parcours',
    'course_mode_depart':'Course · Mode de départ',
    'position_autostart':'Autostart · Position assignée',
    'ligne_autostart':'Autostart · Ligne',
    'capacite_autostart':'Autostart · Capacité première ligne',
    'recul_depart_m':'Départ · Recul (m)',
    'synthese_actualite':'Synthèse des avis',
    'ml_modele_statut':'ML · État du modèle',
    'ml_rang':'ML · Rang',
    'version_ml_utc':'ML · Calcul UTC',
    'ml_top3':'ML · Sélection',
    'ml_proba_podium':'ML · Probabilité calibrée',
    'ml_score_non_calibre':'ML · Score non calibré',
    'top3_cotes_valeur':'Cotes · Valeur',
    'cote_releve_utc':'Cotes · Relevé UTC',
    'cote_rapport_utc':'Cotes · Rapport PMU UTC',
    'top3_cotes_top3':'Cotes · Sélection',
    'top3_cotes_rang':'Cotes · Rang',
    'top3_cotes_statut':'Cotes · État',
    'top3_direct_utc':'TOP3 direct · Calcul UTC',
    'top3_cotes_utc':'TOP3 cotes · Calcul UTC',
    'arrivee_rang':'Arrivée · Rang officiel',
    'meteo_resume':'Météo · Synthèse',
    'meteo_statut':'Météo · État',
    'extraction_utc':'Capture historique · UTC',
}
DISPLAY_NAMES.update({
    'reunion_pmu': 'Réunion PMU',
    'rapprochement_statut': 'État du rapprochement',
    'rapprochement_arrivee_statut': 'État de l’arrivée PMU',
    'rapprochement_declenchement_utc': 'Rapprochement · Déclenchement UTC',
    **{f'score_{phase}_{kind}': f'Score H-{phase[1:]} · {kind.upper() if kind == "ml" else "Direct"}'
       for phase in ('h2', 'h1') for kind in ('direct', 'ml')},
})
INVERSE_NAMES = {label:key for key,label in DISPLAY_NAMES.items()}
assert len(INVERSE_NAMES)==len(DISPLAY_NAMES)
INVERSE_NAMES.update({'Ferrure':'ferrure', 'PMU · Complétude fiche':'actuel_statut',
                      'Experts · Disponibilité par source':'couverture_experts'})


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
    for x in data.get('inventaire_reunions', []):
        if x.get('code')==code:return x
    return {}


def champs_course_pmu(info):
    params = info.get('parametres_pmu') or {}
    conditions = params.get('conditions') or ''
    category = re.search(r'\b(?:Groupe [IVX]+|Course [A-Z])\b', conditions, re.IGNORECASE)
    ages = re.search(
        r'\bPour\b[^,.;]{0,100}?\b(\d{1,2}(?:(?:\s*(?:à|et)\s*|\s*,\s*)\d{1,2})*)\s+ans\b',
        conditions, re.IGNORECASE)
    from .departs_trot import mode_pmu
    mode, _ = mode_pmu(info)
    return {
        'course_nom_pmu': info.get('nom') or '',
        'course_categorie_pmu': category.group() if category else '',
        'course_ages_admis': f'{ages.group(1)} ans' if ages else '',
        'course_allocation_eur': info.get('allocation_eur') or params.get('montantPrix'),
        'course_parcours': (params.get('parcours') or '').capitalize(),
        'course_mode_depart': mode,
    }


def course_key(date,hippodrome,code):
    hip=str(hippodrome).strip().upper()
    for prefix in ('HIPPODROME DE PARIS-', 'HIPPODROME DE ', "HIPPODROME D'", 'HIPPODROME DU ', 'HIPPODROME DES '):
        if hip.startswith(prefix):hip=hip[len(prefix):];break
    return '|'.join([date,hip,code])


def selection_predepart(prediction, departure, now):
    """Numéros du TOP3 enregistré, dans l'ordre de la prévision."""
    from .echeances_production import instant
    depart = instant(departure)
    created = instant(prediction.get('calcul_utc'))
    if not depart or not created or not now.tzinfo or not created < depart or created > now:
        return []
    try:
        selected = [int(h['numero']) for h in prediction['top3']]
        withdrawn = {int(n) for n in prediction.get('non_partants_confirmes', [])}
    except (KeyError, TypeError, ValueError, OverflowError):
        return []
    if len(selected) != 3 or len(set(selected)) != 3 or set(selected) & withdrawn:
        return []
    return selected if all(1 <= n <= 30 for n in selected) else []


def matching_pct(prediction, arrival, departure, now=None):
    """Score 0–100, uniquement avec preuves temporelles et podium unique."""
    from .echeances_production import instant
    now = now or datetime.now(timezone.utc)
    depart = instant(departure)
    checked = instant(arrival.get('verifie_utc'))
    if not depart or not checked or not now.tzinfo or not depart < checked <= now:
        return ''
    selected = selection_predepart(prediction, departure, now)
    if not selected:
        return ''
    try:
        podium=sorted((h for h in arrival['arrivee'] if h['rang'] in (1,2,3)),key=lambda h:h['rang'])
        if [h['rang'] for h in podium]!=[1,2,3]:return ''
        actual={int(h['numero']) for h in podium}
        if len(actual)!=3 or not all(1<=n<=30 for n in actual):return ''
        return round(100*len(actual&set(selected))/3,2)
    except (KeyError,TypeError,ValueError,OverflowError):
        return ''


def conclusion_methodes(scores):
    """Comparer exclusivement les scores temporellement vérifiés, sans faux gagnant."""
    valid={name:round(value*3/100) for name,value in scores.items()
           if isinstance(value,(int,float)) and value in (0,33.33,66.67,100)}
    if not valid:
        return 'Aucune prévision indépendante évaluable avant cette arrivée'
    if len(valid)==1:
        name,hits=next(iter(valid.items()))
        return f'{name} : {hits}/3 ; aucune autre méthode évaluable'
    best=max(valid.values())
    names=', '.join(name for name,hits in valid.items() if hits==best)
    if best==0:
        return 'Échec commun : aucun cheval retrouvé (0/3)'
    if sum(hits==best for hits in valid.values())>1:
        return f'Égalité en tête : {names} ({best}/3)'
    return f'Meilleure méthode : {names} ({best}/3)'


def source_rows(cache):
    from .partants_actuels_v21 import profil_pmu_exclusif
    from .cotes_v19 import cote_valide, dernier_releve
    from .identites_chevaux import IndexGeny
    identites_geny = IndexGeny(cache)
    courses, history, reports = {}, {}, {}
    now = datetime.now(timezone.utc)
    from .cycle_ml_actif import modele_disponible,STATUT
    candidat_disponible=modele_disponible(cache) is not None
    def statut_ml(document,depart):
        if document.get('statut'):return document['statut']
        if candidat_disponible:
            departure = instant_iso(depart)
            if departure and departure <= now:
                return 'ML_NON_PUBLIE_AVANT_DEPART'
            return STATUT+'_SANS_PREVISION'
        return 'ML_NON_ENTRAINE'
    import unicodedata
    from .sources_experts_v23 import champs_sheet
    from .avis_24h_trot import champs_sheet as champs_24h
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
            actual=profil_pmu_exclusif((participant.get('chevaux') or {}).get(str(n),{}))
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
                 **champs_course_pmu(info),
                 'heure_depart_paris':depart,'discipline':info.get('discipline',''),
                 'distance_m':info.get('distance_m',''),'numero':n,'cheval':r.get('nom',''),
                 'driver_jockey':actual.get('driver_jockey',''),
                 'entraineur':actual.get('entraineur',''),
                 'proprietaire':actual.get('proprietaire',''),
                 'ferrure':actual.get('ferrure',''),
                 'non_partant':r.get('statut_np',''),
                 'historique_statut':historique.get('historique_statut',''),
                 'historique_nb_courses_datees':historique.get('nombre_performances_persistantes',''),
                 'historique_maj_utc':historique.get('historique_maj_utc',''),
                 'actuel_statut':actual.get('ferrure_qualification') or ('PMU_FERRURE_DISPONIBLE' if (actual or {}).get('ferrure') else 'PMU_FERRURE_NON_RECUPEREE') if actual else 'PMU_PARTANTS_NON_RECUPERES',
                 'actuel_maj_utc':participant.get('capture_utc',''),
                 'statut_prevision':forecast_state,
                 'fige_utc':frozen.get('frozen_at',''),
                 'mode_calcul_top3':'BASELINE_HISTORIQUE' if has_historical else ('ML' if has_ml else 'NON_CALCULE'),
                 'historique_modele_statut':'FIGE' if has_historical else 'NON_CALCULE',
                 'ml_modele_statut':statut_ml(ml,depart),
                 'secours_statut':'NON_CALCULE',
                 'baseline_top3':'OUI' if any(str(h.get('numero'))==str(n) for h in frozen.get('top3',[])) else '',
                 'baseline_final_top3':'OUI' if any(str(h.get('numero'))==str(n) for h in (latest or frozen).get('top3',[])) else '',
                 'rang_top3':r.get('baseline_final_rang','') if r.get('baseline_final_top3')=='OUI' else ''}
            for c in COMPARE_COLUMNS:
                 if c not in doc and c not in PROFILE_COLUMNS:doc[c]=r.get(c,'')
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
                            'etat_ml':statut_ml(ml,depart),
                            'source_export':str(path.relative_to(cache)),
                            'derniere_sync_utc':datetime.now(timezone.utc).isoformat(),
                            'statut_evaluation':'EVALUE' if comparison_present and r.get('baseline_final_hits_course') else 'ARRIVEE_SANS_TOP3_FIGE'}
    # PMU seul : creer la fiche de chaque partant meme sans manifeste/historique Geny.
    # Les trois paliers sont independants; aucun score n'est invente.
    course_files = {path.name for folder in ('partants_actuels', 'cotes')
                    for path in (cache/folder).glob('????-??-??_R*C*.json')}
    for filename in sorted(course_files):
        match=re.fullmatch(r'(\d{4}-\d{2}-\d{2})_(R\d+C\d+)\.json',filename)
        if not match:continue
        date,code=match.groups()
        info=course_info(cache,code,date)
        if not info:continue
        participant=load_json(cache/'partants_actuels'/filename)
        official=load_json(cache/'arrivees'/f'{date}_{code}.json')
        official_ranks={str(h.get('numero')):h['rang'] for h in official.get('arrivee',[])
                        if isinstance(h.get('rang'),int) and h['rang']>0}
        direct=load_json(cache/'pronostics'/f'{date}_{code}_direct.json')
        marche=load_json(cache/'pronostics'/f'{date}_{code}_cotes.json')
        cotes_source = dernier_releve(cache, {**info, 'date': date, 'code': code})
        cotes_releve = {str(h['numero']): h for h in cotes_source.get('chevaux', [])}
        participants = {n: {'nom': h.get('nom'), 'statut_np': h.get('statut_np')}
                        for n, h in cotes_releve.items()}
        participants.update(participant.get('chevaux') or {})
        selection_cotes = {n: rank for rank, n in enumerate(
            selection_predepart(marche, info.get('depart', ''), now), start=1)}
        cotes_etat = marche.get('statut', '') if selection_cotes else (
            'DONNEES_INSUFFISANTES' if marche or cotes_source else 'PAS_DE_RELEVE')
        ml=load_json(cache/'pronostics'/f'{date}_{code}_ml_latest.json')
        avis_experts=load_json(cache/'avis_experts'/f'{date}_{code}.json')
        avis_24h = load_json(cache/'avis_editoriaux'/f'{date}_{code}.json')
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
        criteres = champs_course_pmu(info)
        ranks={}
        for mode,document in (('direct',direct),('cotes',marche if selection_cotes else {}),('ml',ml)):
            ranks[mode]={str(h.get('numero')):(i,h) for i,h in
                         enumerate(document.get('classement_complet',[]),start=1)}
        from .echeances_production import instant
        from .liaison_chevaux_v22 import etablir, nom_normalise
        from .profils_partants import afficher_profils
        calcul = instant(direct.get('calcul_utc'))
        depart = instant(info.get('depart'))
        leaders = {}
        for mode, document in (('direct', direct), ('ml', ml)):
            selection = selection_predepart(document, info.get('depart', ''), now)
            if selection:
                leaders[mode] = str(selection[0])
        profils_predits = direct.get('profils_partants', {}) if (
            direct.get('version_profils') and calcul and depart and calcul < depart
            and instant(direct.get('depart')) == depart) else {}
        liens=etablir(cache,{'date':date,'code':code},[
            {'numero':n,'nom':v.get('nom',''),'age_ans':v.get('age_ans')}
            for n,v in participants.items()
        ],index=identites_geny)
        for n,act in participants.items():
            act=profil_pmu_exclusif(act)
            krow=f'{k}|{n}'
            existing=courses.get(krow,{})
            direct_rank,direct_h=ranks['direct'].get(str(n),('',{}))
            cote_observee = cotes_releve.get(str(n), {})
            statut_np = act.get('statut_np') or cote_observee.get('statut_np') or 'NP_NON_VERIFIE'
            if cote_observee.get('statut_np') == 'NON_PARTANT':
                statut_np = 'NON_PARTANT'
            cote_heure = instant(cote_observee.get('heure_utc'))
            valeur_cote = cote_valide(cote_observee.get('cote')) if (
                statut_np != 'NON_PARTANT' and cote_heure and depart and cote_heure < depart
                and cote_heure <= now) else None
            depart_trot = act.get('depart_trot', {})
            capture_depart = instant(depart_trot.get('capture_utc'))
            if not (depart_trot.get('source') == 'PMU_API_PARTICIPANTS' and capture_depart
                    and depart and capture_depart < depart and capture_depart <= now
                    and statut_np == 'PARTANT'):
                depart_trot = {}
            ml_rank,ml_h=ranks['ml'].get(str(n),('',{}))
            avis=(avis_experts.get('chevaux') or {}).get(str(n),{})
            link=liens.get(str(n),{})
            link_method=link.get('methode','NON_ASSOCIE')
            hist=link.get('historique',{})
            hist_status=(
                'HISTO_PARTIEL_GENY' if hist.get('statut') in ('PARTIEL', 'PARTIEL_HISTORIQUE')
                else 'GENY_IDENTIFIE_CARRIERE_MANQUANTE' if link.get('cheval_id') and not hist
                else 'HISTO_OK_NOM_ID' if link_method in ('NOM_EXACT_ET_ID_GENY_CONFIRME','NOM_AMBIGU_ID_CONFIRME','ID_GENY_MANIFESTE_VERIFIE')
                else 'HISTO_OK_NOM' if link_method=='NOM_EXACT_UNIQUE'
                else 'HISTO_AMBIGU' if link_method=='NOM_AMBIGU'
                else 'HISTO_NON_COLLECTE')
            current={
                **champs_sheet(avis_experts,n,act.get('nom','')),
                **(champs_24h(avis_24h, n, act.get('nom', ''), depart, now) if statut_np == 'PARTANT' else {}),
                **criteres,
                'meteo_resume':meteo_resume,
                'meteo_statut':meteo_statut,
                'historique_statut':hist_status,
                'historique_nb_courses_datees':len(hist.get('performances',[])) if hist else '',
                'historique_maj_utc':status.get(link.get('cheval_id'),{}).get('maj_utc','') if hist else '',
                'course_key':k,'date_course':date,'hippodrome':hip,'rncn':code,
                'heure_depart_paris':info.get('depart',''),
                'discipline':info.get('discipline',''),
                'distance_m':info.get('distance_m',''),
                'numero':str(n),'cheval':act.get('nom','') or cote_observee.get('nom') or existing.get('cheval',''),
                'driver_jockey':act.get('driver_jockey',''),
                'entraineur':act.get('entraineur',''),
                'proprietaire':act.get('proprietaire',''),
                'ferrure':act.get('ferrure',''),
                'musique_pmu':act.get('musique_pmu',''),
                'age_ans':act.get('age_ans') if act.get('age_ans') is not None else '',
                'sexe':act.get('sexe',''),
                'gains_euros':act.get('gains_euros') if act.get('gains_euros') is not None else '',
                'non_partant':statut_np,
                'arrivee_rang':official_ranks.get(str(n),''),
                'actuel_statut':act.get('ferrure_qualification') or ('FERRURE_DISPONIBLE_SOURCEE' if act.get('ferrure') else 'FERRURE_NON_RECUPEREE') if act else 'PMU_PARTANTS_NON_RECUPERES',
                'actuel_maj_utc':participant.get('capture_utc',''),
                'top3_direct_rang':direct_rank,
                'top3_direct_score':direct_h.get('score_direct',''),
                'top3_direct_top3':'OUI' if direct_rank and direct_rank<=3 else '',
                'top3_direct_statut':direct.get('statut','NON_CALCULE'),
                'top3_direct_source_forme':direct_h.get('source_forme',''),
                'top3_direct_qualite':direct_h.get('qualite_score',''),
                'top3_direct_historiques_exploites':direct_h.get('historique_exploitable','') if direct_rank else '',
                'position_autostart':depart_trot.get('position', ''),
                'ligne_autostart':depart_trot.get('ligne', ''),
                'capacite_autostart':depart_trot.get('capacite', ''),
                'recul_depart_m':depart_trot.get('recul_m', ''),
                'top3_cotes_valeur':valeur_cote if valeur_cote is not None else '',
                'cote_releve_utc':cote_observee.get('heure_utc', '') if valeur_cote is not None else '',
                'cote_rapport_utc':cote_observee.get('date_rapport_utc', '') if valeur_cote is not None else '',
                'top3_cotes_top3':'OUI' if int(n) in selection_cotes and statut_np != 'NON_PARTANT' else '',
                'top3_cotes_rang':selection_cotes.get(int(n), '') if statut_np != 'NON_PARTANT' else '',
                'top3_cotes_statut':cotes_etat,
                'ml_rang':ml_rank,
                'ml_score_non_calibre':ml_h.get('score_non_calibre',ml_h.get('proba_podium_estimee','')),
                'ml_top3':'OUI' if ml_rank and ml_rank<=3 else '',
                'ml_modele_statut':statut_ml(ml,info.get('depart','')),
                'statut_prevision':'PREVISIONS_DISPONIBLES' if any(ranks[mode] for mode in ('direct','cotes','ml')) else existing.get('statut_prevision','TOP3_NON_CALCULE'),
                'mode_calcul_top3':'DIRECT+COTES+ML_SEPARES' if any(ranks[mode] for mode in ('direct','cotes','ml')) else existing.get('mode_calcul_top3','NON_CALCULE'),
                'top3_direct_utc':direct.get('calcul_utc',''),
                'top3_cotes_utc':marche.get('calcul_utc','') if selection_cotes else '',
                'version_ml_utc':ml.get('calcul_utc',''),
            }
            facts=act.get('divergences_sources',[])
            if facts:
                current['divergences_sources']+=' ; '+ '; '.join(f"{x['champ']}: {x['valeur_retenue']} / {x['source']}={x['valeur_tiers']}" for x in facts)
            # Une version prédictive présente fait foi, y compris pour les
            # champs vides (retrait NP, sélection devenue insuffisante).
            # Un fichier absent, en revanche, n'autorise pas un effacement.
            authoritative=set(EXPERT_COLUMNS)
            for mode, document in (('direct', direct), ('ml', ml)):
                field = f'gagnant_{mode}_selection'
                if document or act.get('statut_np') == 'NON_PARTANT':
                    current[field] = ('OUI' if str(n) == leaders.get(mode)
                                      and act.get('statut_np') == 'PARTANT' else '')
                    authoritative.add(field)
            if direct:
                authoritative.update(('top3_direct_rang','top3_direct_score','top3_direct_top3',
                    'top3_direct_source_forme','top3_direct_qualite','top3_direct_historiques_exploites'))
            signal = profils_predits.get(str(n))
            nom = nom_normalise(act.get('nom'))
            np = act.get('statut_np') == 'NON_PARTANT' or any(
                str(numero) == str(n) for numero in direct.get('non_partants_confirmes', []))
            if np or (signal and nom):
                identite_confirmee = signal and nom == nom_normalise(signal.get('nom'))
                current['profil_partant'], current['profil_partant_indices'] = (
                    afficher_profils(signal) if identite_confirmee and not np else ('', ''))
                authoritative.update(PROFILE_COLUMNS)
            if marche or cotes_source or statut_np == 'NON_PARTANT':
                authoritative.update(('top3_cotes_top3', 'top3_cotes_rang', 'top3_cotes_utc'))
            if cotes_source or statut_np == 'NON_PARTANT':
                authoritative.update(('top3_cotes_valeur', 'cote_releve_utc', 'cote_rapport_utc'))
            if depart_trot or statut_np == 'NON_PARTANT':
                authoritative.update(DEPART_COLUMNS)
            if ml:
                authoritative.update(('ml_rang','ml_top3','ml_score_non_calibre'))
            courses[krow]={**existing,**{key:value for key,value in current.items()
                                         if value is not None and (value!='' or key in authoritative)}}
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
        scores_by_mode = {
            name:matching_pct(doc,arrivee,info.get('depart',''),now)
            for name,doc in (('Direct',direct),('ML',ml))}
        conclusion=conclusion_methodes(scores_by_mode)
        reports[k]={**existing,
                    'etat_ml':statut_ml(ml,info.get('depart','')),
                    'top3_direct_calcule_utc':direct.get('calcul_utc',''),
                    'conclusion':conclusion,
                    'top3_direct_numeros':direct_nums,'score_direct':direct_hits,
                    'top3_cotes_numeros':cote_nums,'score_cotes':cote_hits,
                    'top3_ml_numeros':ml_nums,'score_ml':ml_hits,
                    'matching_direct_pct':scores_by_mode['Direct'],
                    'matching_ml_pct':scores_by_mode['ML'],
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
        def nom_partant(numero):
            return str(courses.get(f'{k}|{numero}', {}).get('cheval') or '').strip()

        for numeros, noms in REPORT_NAME_COLUMNS.items():
            selection = reports[k].get(numeros)
            if selection:
                ordered_names = [nom_partant(n) for n in selection.split(',')]
                if all(ordered_names):
                    reports[k][noms] = ' · '.join(ordered_names)
        for mode, document, matching_value in (
            ('direct', direct, scores_by_mode['Direct']), ('ml', ml, scores_by_mode['ML'])
        ):
            prefix = f'gagnant_{mode}_'
            if matching_value == '':
                reports[k].update({prefix + field: '' for field in ('numero', 'nom', 'rang', 'verdict')})
                continue
            number = int(document['top3'][0]['numero'])
            name = nom_partant(number)
            if name:
                reports[k][prefix + 'nom'] = name
            ranks = [h['rang'] for h in arrivee['arrivee']
                     if str(h.get('numero')) == str(number) and type(h.get('rang')) is int and h['rang'] > 0]
            reports[k].update({
                prefix + 'numero': number,
                prefix + 'rang': ranks[0] if len(ranks) == 1 else '',
                prefix + 'verdict': 'Trouvé' if number == int(podium[0]['numero']) else 'Non trouvé',
            })
    for file in sorted((cache/'rapprochements').glob('????-??-??_R*.json')):
        report = load_json(file)
        date = report.get('date', '')
        for code, row in report.get('courses', {}).items():
            info = course_info(cache, code, date)
            if not info:
                continue
            key = course_key(date, info.get('hippodrome', ''), code)
            report_row = reports.setdefault(key, {
                'course_key': key, 'date_course': date, 'rncn': code,
                'hippodrome': info.get('hippodrome', ''), 'heure_depart_paris': info.get('depart', '')})
            report_row.update(reunion_pmu=report['reunion'], rapprochement_statut=report['statut'],
                              rapprochement_arrivee_statut=row['statut'],
                              rapprochement_declenchement_utc=report['declenchement_utc'])
            for label, score in row['scores'].items():
                report_row['score_' + label.lower()] = score['hits_top3']
            # Les vues historiques conservent leur schéma. Pour une réunion
            # rapprochée, afficher la dernière paire réellement attestée.
            pairs = ((row['scores'].get(f'{phase}_direct'), row['scores'].get(f'{phase}_ml'))
                     for phase in ('H1', 'H2'))
            pair = next((pair for pair in pairs if all(pair)), None)
            if not pair:
                report_row['statut_evaluation'] = ('ARRIVEE_SANS_TOP3_PUBLIE' if row['statut'] == 'ARRIVEE_OFFICIELLE'
                                                   else 'ARRIVEE_NON_VERIFIEE')
            else:
                scores = {}
                for method, item in zip(('direct', 'ml'), pair):
                    numbers = item['numeros']
                    report_row[f'top3_{method}_numeros'] = ','.join(map(str, numbers))
                    report_row[f'score_{method}'] = item['hits_top3']
                    score = round(item['hits_top3'] * 100 / 3, 2)
                    report_row[f'matching_{method}_pct'] = score
                    scores[method.upper() if method == 'ml' else 'Direct'] = score
                    names = [courses.get(f'{key}|{n}', {}).get('cheval', '') for n in numbers]
                    report_row[f'top3_{method}_noms'] = ' · '.join(names) if all(names) else ''
                    official = load_json(cache/'arrivees'/f'{date}_{code}.json')
                    ranks = {horse['numero']: horse['rang'] for horse in official.get('arrivee', [])}
                    report_row.update({
                        f'gagnant_{method}_numero': numbers[0],
                        f'gagnant_{method}_nom': names[0],
                        f'gagnant_{method}_rang': ranks.get(numbers[0], ''),
                        f'gagnant_{method}_verdict': 'Trouvé' if ranks.get(numbers[0]) == 1 else 'Non trouvé',
                    })
                report_row.update(etat_ml=pair[1]['statut_modele'],
                                  top3_direct_calcule_utc=pair[0]['calcul_utc'],
                                  statut_evaluation='EVALUE', conclusion=conclusion_methodes(scores))
    # V31: la provenance textuelle (URL ou descriptif) n'est PAS une
    # identite de course. Les memes performances sont presentes dans les
    # exports de course et les captures persistantes par cheval.
    # Ne jamais doubler un historique lorsque la provenance change.
    grouped={}

    def identite_sportive(r):
        """Champs stables d'une performance, independants de sa provenance Geny."""
        return tuple(str(r.get(field) or '').strip().upper() for field in
                     ('discipline', 'distance_m', 'classement', 'chrono'))

    def qualite_source(value):
        s=str(value or '').strip()
        return (bool(s) and not s.lower().startswith(('http://', 'https://')), len(s))

    def ajouter_performance(ident, r):
        r=dict(r)
        r.setdefault('_statut_verification','EXTRACTION_GENY')
        date=str(r.get('date') or '').strip()
        hip=str(r.get('hippodrome') or '').strip()
        if not ident or not date or not hip:
            return
        base=f'{ident}|{date}|{hip.upper()}'
        identite=identite_sportive(r)
        variants=grouped.setdefault(base,{})
        if identite not in variants:
            variants[identite]=dict(r)
            return
        # Fusion non destructive : completer les champs absents, donner la
        # priorite au descriptif detaille par rapport a l'URL contextuelle.
        saved=variants[identite]
        old_source=saved.get('texte_source','')
        for field,value in r.items():
            if value is not None and str(value) and not str(saved.get(field) or ''):
                saved[field]=value
        if qualite_source(r.get('texte_source'))>qualite_source(old_source):
            saved['texte_source']=r['texte_source']

    for path in sorted((cache/'exports').glob('GENY-*/performances.csv')):
        try: perfs=read_csv(path)
        except (OSError,ValueError):continue
        for r in perfs:
            ajouter_performance(str(r.get('cheval_id') or '').strip(),r)
    # Les captures persistantes contiennent les memes courses mais parfois
    # un texte plus riche. Elles enrichissent plutot qu'elles ne dupliquent.
    journal=load_json(cache/'etat_persistant.json').get('chevaux',{})
    for file in (sorted((cache/'historiques').glob('*/historique_geny.json'))+
                 sorted((cache/'historiques_partiels').glob('*/historique_geny.json'))):
        ident=file.parent.name
        doc=load_json(file)
        partial=file.parent.parent.name=='historiques_partiels'
        if (doc.get('statut')!=('PARTIEL_HISTORIQUE' if partial else 'COMPLET')
                or partial and doc.get('identite_verifiee') is not True
                or not isinstance(doc.get('performances'),list)):
            continue
        cheval=journal.get(ident,{}).get('nom','')
        for perf in doc['performances']:
            from .partants_actuels_v21 import ferrure_historique_explicite
            captured=''
            try:
                stamp=datetime.fromisoformat(doc['extrait_utc'])
                if stamp.tzinfo:captured=stamp.astimezone(timezone.utc).isoformat()
            except (KeyError,ValueError,TypeError):pass
            row={'cheval_id':ident,'nom':cheval,**perf,'_capture_historique_utc':captured,
                 '_statut_verification':'EXTRACTION_GENY_PARTIELLE' if partial else 'EXTRACTION_GENY'}
            if not row.get('ferrure'):
                row['ferrure']=ferrure_historique_explicite(perf.get('texte_source',''))
            ajouter_performance(ident,row)
    for base,variants in grouped.items():
        # Reprendre l'ordre historique par provenance pour garder les cles
        # secondaires existantes si deux vraies courses ont eu lieu le meme jour.
        ordered=sorted(variants.values(),key=lambda r:str(r.get('texte_source') or ''))
        for n,r in enumerate(ordered,start=1):
            if n==1:
                k=base
            else:
                source=' '.join(str(r.get('texte_source','')).split())
                signature=source or '|'.join(str(r.get(field,'')) for field in
                                            ('discipline','distance_m','classement','chrono'))
                suffix=hashlib.sha256(signature.encode('utf-8')).hexdigest()[:16]
                k=f'{base}|{suffix}'
            from .partants_actuels_v21 import ferrure_historique_explicite
            doc={out:r.get(inn,'') for out,inn in HIST_MAPPING.items()}
            if not doc.get('ferrure'):
                doc['ferrure']=ferrure_historique_explicite(r.get('texte_source',''))
            doc['cle_performance']=k
            doc['statut_verification']=r.get('_statut_verification','EXTRACTION_GENY')
            history[k]=doc
    return {'Courses & Prévisions':courses,'Historique chevaux':history,'Résultats & Analyse':reports}


def ensure_headers(existing, additions):
    return existing + [x for x in additions if x not in existing]


def plan_sheet(existing_headers,existing_rows,new_items,tab,now=None):
    """Planning sans mutation: met à jour uniquement les colonnes propriétaires du bridge."""
    if tab=='Historique chevaux':
        from .controle_sync_sheets import verifier_source
        verifier_source(new_items)
    keys={'Courses & Prévisions':('course_key','numero'),
          'Historique chevaux':('cle_performance',),
          'Résultats & Analyse':('course_key',)}[tab]
    additions=COMPARE_COLUMNS if tab=='Courses & Prévisions' else REPORT_COLUMNS if tab=='Résultats & Analyse' else ()
    headers=ensure_headers(existing_headers,tuple(additions))
    if not all(x in headers for x in keys):raise ValueError(f'Colonnes cle manquantes pour {tab}: {keys}')
    def rowkey(row):return '|'.join(str(row.get(x,'')).strip() for x in keys)
    present={rowkey(r):idx+2 for idx,r in enumerate(existing_rows) if all(str(r.get(k,'')).strip() for k in keys)}
    # Plusieurs variantes conservées pour une même performance ne doivent pas
    # être arbitrées en écrasant silencieusement la dernière ligne rencontrée.
    ambiguous=set()
    if tab=='Historique chevaux':
        seen=set()
        for row in existing_rows:
            if not all(str(row.get(k,'')).strip() for k in keys):continue
            key=rowkey(row)
            if key in seen:ambiguous.add(key)
            seen.add(key)
    changes=[];append=[]
    for item in new_items.values():
        k=rowkey(item)
        if k in present:
            if k in ambiguous:continue
            # writes only values actually present/nonempty; leaves other cells untouched.
            for name,val in item.items():
                value=sheet_value(name,val)
                before=existing_rows[present[k]-2].get(name,'')
                differs=((before!=value or (isinstance(value,int) and
                           (not isinstance(before,(int,float)) or isinstance(before,bool))))
                         if name in NUMERIC_SCORES or name == 'top3_cotes_valeur' else (before!=value or (isinstance(before,bool) and not isinstance(value,bool)) if name in MATCHING_COLUMNS else str(before)!=str(value)))
                if date_kind(name):
                    if tab != 'Historique chevaux' and date_kind(name) == 'DATE_TIME' and value and not instant_iso(value):
                        continue
                    differs = not meme_date_sheets(name, before, value)
                if name == 'course_allocation_eur':
                    differs = ''.join(str(before).split()) != str(value)
                    if not value:
                        continue
                # Nettoyage ciblé de l'ancien scan texte : PP de petite piste,
                # DA du nom Da Costa. Une vraie ferrure sourcée reste prioritaire.
                if tab=='Historique chevaux' and name=='ferrure' and val=='':
                    from .partants_actuels_v21 import faux_code_ferrure_historique
                    old=existing_rows[present[k]-2]
                    if (str(old.get('source_url',''))==str(item.get('source_url',''))
                            and faux_code_ferrure_historique(item.get('source_url'),before)):
                        changes.append((present[k],headers.index(name)+1,''))
                        continue
                if (name in headers and val is not None and (str(val)!='' or name in CLEARABLE_COLUMNS
                        or tab=='Courses & Prévisions' and name in PARTANT_PMU_COLUMNS)
                        and differs):
                    changes.append((present[k],headers.index(name)+1,value))
        else:
            append.append([sheet_value(h,item.get(h,'')) for h in headers]);present[k]=-1
    return headers,changes,append



def reconcilier_cles_historiques(existing_rows, incoming):
    """Rejouer sous la cle deja publiee si la signature technique a evolue.

    Evite les nouveaux doublons lorsque le texte Geny change ou lorsqu'un
    second hippodrome/course est decouvert au fil des captures.
    """
    from .controle_sync_sheets import cle_sportive
    from .identites_chevaux import canoniser_ligne,cle_inter_sources
    aliases=[(row,canoniser_ligne(row)) for row in existing_rows]
    aliases=[(old,new) for old,new in aliases if str(old.get('identifiant_cheval'))!=str(new.get('identifiant_cheval'))]
    incoming_ids={str(row.get('identifiant_cheval')) for row in incoming.values()}
    alias_ids={str(new['identifiant_cheval']) for old,new in aliases}&incoming_ids
    alias_keys={str(old.get('cle_performance')) for old,new in aliases if str(new['identifiant_cheval']) in alias_ids}
    # Chaque ancienne ligne doit correspondre exactement à une performance
    # canonique avant de modifier son ID ou d'ajouter le reste de la carrière.
    for old,new in aliases:
        if str(new['identifiant_cheval']) not in alias_ids:continue
        matches=[row for row in incoming.values() if cle_inter_sources(row)==cle_inter_sources(new)]
        if len(matches)!=1:
            raise ValueError('PERFORMANCE_INTERSOURCE_NON_CONCORDANTE: '+str(old.get('cle_performance')))
        if old.get('ferrure') and matches[0].get('ferrure') and old['ferrure']!=matches[0]['ferrure']:
            raise ValueError('FERRURE_INTERSOURCE_NON_CONCORDANTE: '+str(old.get('cle_performance')))
    def identity_for(row):
        if str(row.get('identifiant_cheval')) in alias_ids or str(row.get('cle_performance')) in alias_keys:
            return cle_inter_sources(row)
        return cle_sportive(row)
    known={}
    for row in existing_rows:
        identity=identity_for(row)
        if identity is not None:
            if identity in known and identity[0] in alias_ids:
                raise ValueError('CORRESPONDANCE_HISTORIQUE_AMBIGUE')
            known[identity]=str(row.get('cle_performance') or '').strip()
    output={}
    for row in incoming.values():
        candidate=dict(row)
        identity=identity_for(candidate)
        if identity is not None and identity in known:
            candidate['cle_performance']=known[identity]
        key=str(candidate.get('cle_performance') or '').strip()
        if key in output:
            raise ValueError('DOUBLON_CLE_APRES_RAPPROCHEMENT_HISTORIQUE: '+key)
        output[key]=candidate
    return output


def limiter_cours_registre(source, date_debut=LIVE_RESET_DATE):
    """Ne filtre que les onglets operationnels; ne touche jamais aux historiques."""
    result=dict(source)
    for onglet in ('Courses & Prévisions', 'Résultats & Analyse'):
        result[onglet]={key:row for key,row in source[onglet].items()
                        if str(row.get('date_course',''))>=date_debut}
    return result


def lire_feuille_complete(session, base, tab, properties, page_rows=2000, *, raw_dates=False):
    """Lire toutes les lignes sans perdre les positions des plages vides.

    Une lecture limitée aux 5000 premières lignes faisait réinsérer les clés
    déjà présentes plus bas. La pagination borne la taille des réponses API.
    Aucune écriture n'est autorisée si une page n'a pas pu être lue.
    """
    from .lectures_sheets import get_lecture
    grid=properties.get('gridProperties',{})
    height=grid.get('rowCount',0);width=grid.get('columnCount',0)
    if height<1 or width<1 or page_rows<1:
        raise ValueError('Dimensions de feuille absentes ou invalides')
    values=[];pages=[]
    for start in range(1,height+1,page_rows):
        end=min(height,start+page_rows-1)
        name="'"+tab.replace("'","''")+"'!A"+str(start)+":"+colname(width)+str(end)
        pages.append((name,start,end))
    # Les historiques sont étroits et contiennent souvent des pages vides.
    # Regrouper davantage de pages dans ce cas en bornant le nombre de
    # cellules demandé. Le contrôle indépendant des clés reste séparé.
    pages_par_appel = max(1, min(10, 360_000 // (width * page_rows)))
    for offset in range(0,len(pages),pages_par_appel):
        group=pages[offset:offset+pages_par_appel]
        params = {'ranges': [p[0] for p in group], 'majorDimension': 'ROWS'}
        params['valueRenderOption'] = 'UNFORMATTED_VALUE'
        response=get_lecture(session,base+'/values:batchGet',params=params,timeout=60)
        if response.status_code!=200:
            raise RuntimeError(f'Lecture incomplete {tab} lignes {group[0][1]}:{group[-1][2]}, HTTP {response.status_code}')
        ranges=response.json().get('valueRanges')
        if not isinstance(ranges,list) or len(ranges)!=len(group):
            raise ValueError('Lecture Sheets incomplète : plages absentes')
        for (name,start,end),data in zip(group,ranges):
            if not isinstance(data,dict):raise ValueError('Plage Sheets incohérente')
            actual=str(data.get('range','')).rsplit('!',1)
            sheet=actual[0]
            if sheet.startswith("'") and sheet.endswith("'"):sheet=sheet[1:-1].replace("''", "'")
            if (len(actual)!=2 or sheet!=tab or actual[1]!=name.rsplit('!',1)[1]
                    or data.get('majorDimension','ROWS')!='ROWS'):
                raise ValueError('Lecture Sheets incohérente : plage différente')
            rows=data.get('values',[])
            if (not isinstance(rows,list) or any(not isinstance(r,list) for r in rows)
                    or len(rows)>end-start+1):raise ValueError('Page Sheets incohérente')
            values.extend(rows)
            values.extend([[] for _ in range(end-start+1-len(rows))])
    while values and not values[-1]:values.pop()
    if values and not raw_dates:
        headers = canonical_headers(values[0])
        values[1:] = [[depuis_nombre(field, cell) for field, cell in zip(headers, row)] + row[len(headers):]
                      for row in values[1:]]
    return values


def main():
    from .moteur_sheets import ErreurSynchronisation, SynchroniseurSheets
    cache=Path(os.getenv('PMU_CACHE','cache_pmu'))
    spreadsheet=os.getenv('GOOGLE_SHEETS_ID','1BjzDzC6NsLRMax2XjrCIcCIIgz6hyCJ1YTWOa5hiGLo')
    if not os.getenv('GOOGLE_SHEETS_SERVICE_ACCOUNT_JSON'):
        print('SYNC_GOOGLE_SHEETS=NON_CONFIGURE: secret absent');return 0
    engine=None
    try:
        engine=SynchroniseurSheets(cache,spreadsheet)
        if os.getenv('PMU_KPI_ONLY')=='true':engine.synchroniser_kpi()
        elif os.getenv('PMU_KPI_DIFFERE')=='true':
            plan = load_json(Path(os.environ['PMU_PLAN'])) if os.getenv('PMU_PLAN') else {}
            mode = plan.get('mode')
            if mode in ('JALONS', 'RAPPROCHEMENT'):
                source = engine.source()
                if mode == 'JALONS':
                    tab = 'Courses & Prévisions'
                    codes = set(plan['selection'])
                    scope = {key: row for key, row in source[tab].items()
                             if row.get('date_course') == plan['date'] and row.get('rncn') in codes}
                else:
                    tab = 'Résultats & Analyse'
                    reunions = {r['reunion'] for r in plan['rapprochements_dus']}
                    scope = {key: row for key, row in source[tab].items() if row.get('reunion_pmu') in reunions}
                engine.synchroniser_tables({tab: scope}, scope=mode, allow_structure=True)
                if mode == 'RAPPROCHEMENT':
                    values = lire_feuille_complete(engine.session, engine.base, tab, engine.metadata()[tab],
                                                   raw_dates=True)
                    if not values:
                        raise ErreurSynchronisation('Relecture des rapprochements vide')
                    headers = canonical_headers(values[0])
                    visible = {row.get('course_key'): row for row in
                               (dict(zip(headers, values_row)) for values_row in values[1:])}
                    for key, expected in scope.items():
                        actual = visible.get(key, {})
                        if any(not meme_date_sheets(field, expected[field], actual.get(field, ''))
                               for field in RAPPROCHEMENT_COLUMNS if field in expected):
                            raise ErreurSynchronisation('Rapprochement non confirmé dans Sheets : ' + key)
            else:
                engine.synchroniser_cycle(include_kpi=False)
            from .echeances_production import preuves_sheets, sauver
            if os.getenv('PMU_PREUVE_SHEETS'):
                rows = engine.lire_courses(engine.metadata())
                sauver(os.environ['PMU_PREUVE_SHEETS'], preuves_sheets(rows, datetime.now(timezone.utc)))
        else:engine.synchroniser_cycle()
        return 0
    except ErreurSynchronisation as exc:
        print(f'::error title=Synchronisation Sheets::{exc}')
        return 1
    except Exception as exc:
        print(f'::error title=Synchronisation Sheets::Echec du moteur unique : {type(exc).__name__}')
        return 1
    finally:
        if engine:engine.fermer()

if __name__=='__main__':sys.exit(main())

