"""Audit ex post des predictions PMU. Les cotes restent EXCLUES du ML.

Aucune modification de poids du modèle n'est autorisée par ce module.
La comparaison au marché utilise le rang de cote (faible = favori), pas une
probabilité implicite supposée parfaitement calibrée.
"""
from __future__ import annotations
import csv
from datetime import datetime, timezone
from pathlib import Path
from .ml_v19 import load, save
from .cotes_v19 import dernier_releve, instant


def analyser_course(cache, course, manifest):
    cache=Path(cache)
    key=f"{course['date']}_{course['code']}"
    arrival=load(cache/'arrivees'/f'{key}.json',{}) or {}
    actual={int(r['numero']) for r in arrival.get('arrivee',[]) if r.get('rang') in (1,2,3)}
    if len(actual)!=3:
        return 'ARRIVEE_NON_VERIFIEE'
    base=load(cache/'pronostics'/f'{key}_top3.json',{}) or {}
    base_final=load(cache/'pronostics'/f'{key}_baseline_latest.json',{}) or base
    ml=load(cache/'pronostics'/f'{key}_ml_latest.json',{}) or {}
    odds=dernier_releve(cache, course)
    participants=manifest['courses'][0]['partants']
    codes={int(h['numero']):h.get('nom','') for h in participants}
    # N'utiliser que les dernières cotes relevées avant le départ.
    departure = instant(course.get('depart'))
    if not departure:
        return 'DEPART_INVALIDE'
    valid_odds = {h['numero']: h['cote'] for h in odds.get('chevaux', [])
                  if h.get('cote') is not None and (observed := instant(h.get('heure_utc')))
                  and observed < departure}
    market_order=sorted(valid_odds,key=lambda n:(valid_odds[n],n))
    market_rank={n:i for i,n in enumerate(market_order,1)}
    def ranking(doc):
        return {int(x['numero']):i for i,x in enumerate(doc.get('classement_complet',[]),1)}
    rb=ranking(base);rf=ranking(base_final);rm=ranking(ml)
    def summarize(ranks):
        if len(ranks)<3:return {'statut':'NON_DISPONIBLE','hits_top3':None,'top3':[]}
        winners=set(sorted(ranks,key=ranks.get)[:3]);return {'statut':'EVALUE','hits_top3':len(winners & actual),'top3':sorted(winners)}
    reference=summarize(rb);final=summarize(rf);model=summarize(rm)
    # Un ordre de marché n'est suffisamment comparable que si chaque partant
    # déclaré non retiré possède une cote valide. En cas de NP, conserver une
    # comparaison indicative uniquement, sans classer le marché comme gagnant.
    market=summarize(market_rank)
    complete_market=len(valid_odds)==len(participants)
    market['statut']='INDICATIF_COMPLET' if complete_market else ('INDICATIF_PARTIEL' if market_rank else 'NON_DISPONIBLE')
    rows=[]
    for n,name in sorted(codes.items()):
        r={'numero':n,'nom':name,'arrivee_podium':n in actual,'baseline_rang':rb.get(n),
           'baseline_final_rang':rf.get(n),'ml_rang':rm.get(n),'rang_cote':market_rank.get(n),
           'cote_avant_depart':valid_odds.get(n)}
        r['outsider_detecte']=bool(n in actual and n in rm and rm[n]<=3 and market_rank.get(n,0)>3)
        r['outsider_manque']=bool(n in actual and n in rm and rm[n]>3 and market_rank.get(n,0)>3)
        r['favori_marche_manque_par_ml']=bool(n in actual and market_rank.get(n,100)>0 and market_rank.get(n,100)<=3 and rm.get(n,100)>3)
        rows.append(r)
    flags={
        'outsiders_detectes':sum(x['outsider_detecte'] for x in rows),
        'outsiders_manques':sum(x['outsider_manque'] for x in rows),
        'favoris_marche_manques_par_ml':sum(x['favori_marche_manque_par_ml'] for x in rows),
        'avertissement':'Cotes ex post pour diagnostic uniquement. Un classement de marche n est pas une probabilite validee.'
    }
    if model['hits_top3'] is not None and market['hits_top3'] is not None and complete_market:
        flags['comparaison_ml_marche']='ML_MIEUX' if model['hits_top3']>market['hits_top3'] else ('MARCHE_MIEUX' if model['hits_top3']<market['hits_top3'] else 'EGALITE')
    else:flags['comparaison_ml_marche']='NON_COMPARABLE'
    baseline_label = 'baseline_h2' if base.get('jalon_reference') == 'H2' else 'baseline_h1'
    doc={'course':key,'course_id':manifest['courses'][0].get('course_id'),
         'audit_utc':datetime.now(timezone.utc).isoformat(),
         'arrivee_source':arrival.get('source',''),
         'comparaison':{baseline_label:reference,'baseline_finale':final,'ml':model,'marche_indicatif':market},
         'diagnostic':flags,'chevaux':rows,
         'garde_fous':['Aucune cote parmi les features ML','Ne pas changer les poids apres une course isolee',
                      'Verifier que les predictions precedaient le depart','Aucune conclusion causale sans preuve',
                      'Comparer les memes courses et conditions de disponibilite']}
    folder=cache/'audits';folder.mkdir(parents=True,exist_ok=True)
    save(folder/f'{key}.json',doc)
    return 'AUDIT_ENREGISTRE'


def bilan_global(cache):
    """Résumé descriptif uniquement, aucune ré-optimisation automatique."""
    root=Path(cache)/'audits';files=sorted(root.glob('*.json')) if root.exists() else []
    all_rows=[]
    for file in files:
        d=load(file,{}) or {};comparison=d.get('comparaison',{})
        all_rows.append({'course':d.get('course',file.stem),
            'baseline_h1':comparison.get('baseline_h1',{}).get('hits_top3'),
            'baseline_h2':comparison.get('baseline_h2',{}).get('hits_top3'),
            'baseline_finale':comparison.get('baseline_finale',{}).get('hits_top3'),
            'ml':comparison.get('ml',{}).get('hits_top3'),
            'marche_indicatif':comparison.get('marche_indicatif',{}).get('hits_top3'),
            'marche_statut':comparison.get('marche_indicatif',{}).get('statut'),
            'comparaison_ml_marche':d.get('diagnostic',{}).get('comparaison_ml_marche')})
    if not all_rows:return 'AUCUN_AUDIT'
    path=root/'bilan_comparatif.csv'
    with path.open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(all_rows[0]),delimiter=';');w.writeheader();w.writerows(all_rows)
    return str(path)
