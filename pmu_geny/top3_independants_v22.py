"""TOP3 direct avec contexte PMU/Geny verifie; TOP3 cotes independant.
Jamais de cotes dans la methode directe, ni de donnees apres depart.
"""
from __future__ import annotations
import re
from datetime import datetime, timezone
from pathlib import Path
from .ml_v19 import load, save, numeric
from .auto_v18 import _list, _num
from .profils_partants import (
    CRACK, HAUT_POTENTIEL, PRIORITE, VERSION_PROFILS,
    detecter_crack, detecter_haut_potentiel, sorties_verifiees,
)

VERSION_MOTEUR = 'direct-v32-contextuel'

def _musique(value):
    if isinstance(value,dict):
        value=value.get('musique') or value.get('libelle') or ''
    if not isinstance(value,str):return []
    # Les performances PMU sont souvent collees. Une annee n'est pas une place.
    value=re.sub(r'\(\s*\d{2}(?:\d{2})?\s*\)', ' ', value)
    pattern=r'\d{1,2}[am]|[datr][am]'
    tokens=re.findall(pattern,value,flags=re.I)
    if tokens:
        residue=re.sub(pattern,'',value,flags=re.I)
    else:
        # Compatibilite des archives sans indication d'allure: 1-2-3, D 4 5.
        pattern=r'\d{1,2}|[datr]'
        tokens=re.findall(pattern,value,flags=re.I)
        residue=re.sub(pattern,'',value,flags=re.I)
    if re.sub(r'[\s,;/|.\-]+','',residue):return []
    return tokens[:5]

def _form_score(participant):
    value=next((participant[k] for k in ('musique','musiqueCheval','derniereMusique')
                if participant.get(k)),None)
    series=_musique(value)
    if not series:return None
    points={1:5.0,2:3.5,3:2.5,4:1.5,5:1.0}
    ranks=[int(re.match(r'\d+',t).group()) if t[0].isdigit() else 0 for t in series]
    return round(sum(points.get(r,0.0)*(1-0.12*i) for i,r in enumerate(ranks)),3)

def calculer(cache,course,raw,now=None,clock=None):
    now=now or datetime.now(timezone.utc)
    depart=datetime.fromisoformat(course['depart'])
    if now.tzinfo is None or depart.tzinfo is None:raise ValueError('Fuseau obligatoire')
    if now>=depart:return {'direct':'APRES_DEPART','cotes':'APRES_DEPART'}
    participants=_list(raw,'participants','partants')
    if not participants:return {'direct':'PARTANTS_ABSENTS','cotes':'PARTANTS_ABSENTS'}
    from .formes_contextuelles_v32 import noter_partant
    from .liaison_chevaux_v22 import etablir
    from .partants_actuels_v21 import extraire_partants
    profils=extraire_partants(raw)
    # Les critères courants proviennent exclusivement du relevé PMU fourni.
    identites=[]
    for partant in participants:
        if not isinstance(partant,dict):continue
        num=_num(partant,'numPmu','num','numero','numeroPmu')
        nom=next((str(partant.get(k,'')).strip() for k in ('nomCheval','nom','nomParticipant')
                  if isinstance(partant.get(k),str) and partant.get(k).strip()),'')
        if num is not None and nom:identites.append({'numero':num,'nom':nom})
    # Un nom exact unique ou un identifiant Geny confirme est obligatoire.
    liens=etablir(cache,course,identites)
    base=Path(cache)/'pronostics'/f"{course['date']}_{course['code']}"
    expected=course.get('nombre_declares')
    old_docs={mode:load(Path(str(base)+f'_{mode}.json'),{}) or {} for mode in ('direct','cotes')}
    known_np=set()
    for old in old_docs.values():
        try:
            if datetime.fromisoformat(old['calcul_utc'])<=now and old.get('depart')==course['depart']:
                known_np.update(int(n) for n in old.get('non_partants_confirmes',[]))
        except (KeyError,TypeError,ValueError):continue
    all_numbers=set()
    eligible=[];direct=[];market=[]
    signaux = {}
    for item in participants:
        if not isinstance(item,dict):continue
        n=_num(item,'numPmu','num','numero','numeroPmu')
        if n is None or n in all_numbers:
            return {'direct':'PARTANTS_INCOHERENTS','cotes':'PARTANTS_INCOHERENTS'}
        all_numbers.add(n)
        if item.get('nonPartant') is True or str(item.get('statut','')).upper() in ('NP','NON_PARTANT'):
            known_np.add(n)
            continue
        if item.get('nonPartant') is False or str(item.get('statut','')).upper()=='PARTANT':
            known_np.discard(n)  # Nouvelle confirmation explicite PMU.
        if n in known_np:continue
        eligible.append(n)
        label=next((str(item.get(k,'')) for k in ('nomCheval','nom','nomParticipant') if item.get(k)),'')
        profil = profils.get(n, {})
        lien = liens.get(str(n), {})
        info=noter_partant(item,course,lien,profil)
        if label:
            sorties = sorties_verifiees(course, lien, now) if profil.get('statut_np') == 'PARTANT' else []
            gains = profil.get('gains_euros')
            crack = detecter_crack(sorties, gains)
            potentiel = detecter_haut_potentiel(sorties, profil.get('age_ans'))
            signaux[str(n)] = {
                'nom': label,
                'statut': CRACK if crack else HAUT_POTENTIEL if potentiel else '',
                'crack': crack,
                'gains_carriere_euros': gains,
                'haut_potentiel': potentiel,
                'sorties_verifiees': sum(sortie.points is not None for sortie in sorties),
            }
            if sorties:
                signaux[str(n)].update(
                    historique_extrait_utc=lien['historique']['extrait_utc'],
                    source_historique=lien['historique']['source_url'],
                    identifiant_historique=lien['cheval_id'],
                )
        if info['score'] is not None and label:
            direct.append({'numero':n,'nom':label,'score_direct':info['score'],
                           'source_forme':info['source_forme'],
                           'qualite_score':info['qualite'],
                           'musique_exploitable':info['musique_exploitable'],
                           'historique_exploitable':info['historique_exploitable'],
                           'distance_proche':info.get('distance_proche',0),
                           'comparabilite_moyenne':info.get('comparabilite_moyenne'),
                           'ferrures_historiques_comparees':info.get('ferrures_historiques_comparees',0),
                           'source_ferrure_courante':profils.get(n,{}).get('source_ferrure','PMU' if profils.get(n,{}).get('ferrure') else 'NON_DOCUMENTEE'),
                           'identifiant_historique':info.get('identifiant_historique')})
        cote=None
        for field in ('rapportDirect','coteDirect','cote','rapportProbable'):
            raw_cote=item.get(field)
            if isinstance(raw_cote,dict):raw_cote=raw_cote.get('rapport') or raw_cote.get('valeur')
            x=numeric(raw_cote)
            if x is not None and x>0:cote=x;break
        if cote is not None:market.append({'numero':n,'nom':label,'cote':cote})
    output={}
    for mode,ranking,key in [('direct',direct,'score_direct'),('cotes',market,'cote')]:
        observed_at=now.isoformat()
        reuse_previous = False
        old=old_docs[mode]
        old_ranking=[h for h in old.get('classement_complet',[]) if int(h['numero']) not in known_np]
        old_usable=False
        try:
            old_usable=(datetime.fromisoformat(old['calcul_utc'])<=now and
                        old.get('depart')==course['depart'] and old.get('version_moteur')==VERSION_MOTEUR)
        except (KeyError,ValueError,TypeError):pass
        complete_list=expected is not None and len(all_numbers)==int(expected)
        # Comparer la couverture APRES exclusion des retraits, jamais le nombre brut.
        if old_usable and len(old_ranking)>len(ranking) and not (complete_list and len(eligible)<3):
            if known_np==set(old.get('non_partants_confirmes',[])):
                output[mode]='ANCIEN_RELEVE_PLUS_COMPLET'
                continue
            ranking=old_ranking
            reuse_previous = True
            observed_at=old.get('donnees_observees_utc',old['calcul_utc'])
            if mode == 'direct':
                signaux = {n: signal for n, signal in old.get('profils_partants', {}).items()
                           if int(n) not in known_np}
        if mode == 'direct':
            ranking.sort(key=lambda h: (-h[key], -PRIORITE.get(
                signaux.get(str(h['numero']), {}).get('statut'), 0), h['numero']))
        else:
            ranking.sort(key=lambda h: (h[key], h['numero']))
        sufficient=len(ranking)>=3 and not (complete_list and len(eligible)<3)
        doc={'date':course['date'],'course':course['code'],'depart':course['depart'],
             'calcul_utc':now.isoformat(),'mode':mode.upper(),
             'donnees_observees_utc':observed_at,
             'version_moteur':VERSION_MOTEUR,'non_partants_confirmes':sorted(known_np),
             'statut':('COMPLET' if complete_list and len(ranking)==len(eligible) else 'PARTIEL') if sufficient else 'DONNEES_INSUFFISANTES',
             'observations':len(ranking),'partants_eligibles':len(eligible),
             'classement_complet':ranking if sufficient else [],'top3':ranking[:3] if sufficient else [],
             'note':('Direct heuristique: musique PMU et historiques Geny anterieurs'
                     ' ponderes par discipline, distance, hippodrome, ferrure documentee'
                     ' et anciennete. Scores non calibres; facteurs manquants explicites.'
                     if mode=='direct' else 'Cotes PMU: palier de marche independant.')}
        if mode=='direct':
            if not reuse_previous or old.get('version_profils'):
                doc['version_profils'] = old['version_profils'] if reuse_previous else VERSION_PROFILS
                doc['profils_partants'] = signaux
            doc['couverture_sources']={
                'pmu_musique':sum(h.get('musique_exploitable',0)>0 for h in ranking),
                'geny_historique':sum(h.get('historique_exploitable',0)>0 for h in ranking),
                'pmu_seul':sum(h.get('source_forme')=='PMU_MUSIQUE_SEULE' for h in ranking),
                'sans_score':max(0,len(eligible)-len(ranking)),
                'effectif_declare_confirme':complete_list,
            }
        filename=Path(str(base)+f'_{mode}.json')
        if not sufficient and not old and not known_np and not (mode == 'direct' and any(
                signal['statut'] for signal in signaux.values())):
            output[mode]='DONNEES_INSUFFISANTES'
            continue
        captured=clock() if clock else now
        if captured>=depart:
            output[mode]='APRES_DEPART'
            continue
        doc['calcul_utc']=captured.isoformat()
        doc['premier_calcul_utc']=old.get('premier_calcul_utc',doc['calcul_utc'])
        if old:
            version=datetime.fromisoformat(old['calcul_utc']).astimezone(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
            archive=Path(cache)/'pronostics'/'versions'/f"{course['date']}_{course['code']}_{mode}_{version}.json"
            if not archive.exists():save(archive,old)
        save(filename,doc)
        output[mode]='CALCULE_'+doc['statut'] if sufficient else 'DONNEES_INSUFFISANTES'
    return output
