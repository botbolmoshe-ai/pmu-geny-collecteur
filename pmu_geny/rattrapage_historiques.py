"""Rattrapage à inventaire figé, sans fenêtre de courses ni moteur de collecte parallèle."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from collections import Counter
from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlparse

from . import historiques_incrementaux as inc
from .liaison_chevaux_v22 import nom_normalise

QUEUE=Path('rattrapage_historiques/etat.json')
INVENTAIRE=QUEUE.parent/'inventaire_sheets.json'


def engagement_canonique(value):
    value=str(value or '')
    match=re.fullmatch(r'(\d{4}-\d{2}-\d{2})\|[^|]+\|(R\d+C\d+)',value)
    return match[1]+'_'+match[2] if match else value


def cle_contexte(horse):
    signature='|'.join((nom_normalise(horse.get('nom')),engagement_canonique(horse.get('engagement')),
                        str(horse.get('numero',''))))
    return 'contexte:'+hashlib.sha256(signature.encode()).hexdigest()[:24]


def contexte_verifiable(horse):
    day=engagement_canonique(horse.get('engagement'))
    if re.fullmatch(r'\d{4}-\d{2}-\d{2}_R\d+C\d+',day) and str(horse.get('numero','')).isdigit():
        return (nom_normalise(horse.get('nom')),day,str(horse['numero']))
    return None


def url_cheval(url,ident):
    parsed=urlparse(str(url or ''))
    match=re.match(r'/cheval/(\d+)(?:\D|$)',parsed.path)
    return parsed.scheme=='https' and parsed.hostname in ('geny.com','www.geny.com') and bool(match and match[1]==ident)


def url_course(url):
    parsed=urlparse(str(url or ''))
    return parsed.scheme=='https' and parsed.hostname in ('geny.com','www.geny.com') and bool(re.match(r'/course/\d+',parsed.path))


def inventaire_local(cache,sheets, *, index=None):
    """Toutes les dates, NP inclus ; un nom ambigu n'est pas un identifiant."""
    cache=Path(cache);records=[]
    journal=inc.lire(cache/'etat_persistant.json',{'chevaux':{}})['chevaux']
    for ident,meta in journal.items():
        doc=inc.lire(cache/'historiques'/str(ident)/'historique_geny.json')
        records.append({'id':str(ident),'nom':meta.get('nom',''),'url_geny':doc.get('source_url',''),
                        'origine':'JOURNAL'})
    for file in sorted((cache/'historiques').glob('*/historique_geny.json')):
        doc=inc.lire(file);ident=file.parent.name
        records.append({'id':ident,'nom':journal.get(ident,{}).get('nom') or doc.get('nom',''),
                        'url_geny':doc.get('source_url',''),'origine':'CAPTURE'})
    for file in sorted((cache/'manifestes').glob('*.json')):
        for course in inc.lire(file).get('courses',[]):
            for h in course.get('partants',[]):
                records.append({**h,'id':str(h.get('id','')),
                    'course_url':course.get('source_course_geny',''),'origine':'MANIFESTE:'+file.stem})
    from .sync_google_sheets import read_csv
    for name in ('partants.csv','performances.csv'):
        for file in sorted((cache/'exports').glob('GENY-*/'+name)):
            for h in read_csv(file):
                records.append({'id':str(h.get('cheval_id','')),'nom':h.get('nom',''),
                    'numero':h.get('numero',''),'origine':'EXPORT:'+file.parent.name})
    for key,h in inc.lire(cache/inc.QUEUE,{'chevaux':{}})['chevaux'].items():
        records.append({**h,'url_geny':h.get('geny',{}).get('url_geny',''),
                        'origine':'FILE_PRODUCTION:'+key})
    for file in sorted((cache/'partants_actuels').glob('????-??-??_R*C*.json')):
        cid=inc.course_geny_connue(cache,file.stem)
        course_url='https://www.geny.com/course/'+cid[5:]+'/partants-pronostics' if re.fullmatch(r'GENY-\d+',str(cid)) else ''
        for number,h in inc.lire(file).get('chevaux',{}).items():
            records.append({'nom':h.get('nom',''),'numero':str(number),'engagement':file.stem,
                            'course_url':course_url,'origine':'PMU:'+file.stem})
    records.extend(sheets.get('chevaux',[]))
    from .identites_chevaux import IndexGeny, qualifier_observation
    index = index or IndexGeny(cache, observations=sheets.get('chevaux', []))
    by_id={};unknown=[]
    def merge(target,record):
        name=record.get('nom','')
        if name and target.get('nom') and nom_normalise(name)!=nom_normalise(target['nom']):
            target['conflit_identite']=True
        if name and not target.get('nom'):target['nom']=name
        target.setdefault('origines',[])
        origin=record.get('origine','')
        if origin and origin not in target['origines']:target['origines'].append(origin)
        ident=target.get('id','')
        url=record.get('url_geny') or record.get('geny',{}).get('url_geny','')
        if ident and url_cheval(url,ident):
            target['geny']={'id':ident,'nom':target.get('nom',''),
                            'url_geny':url.replace('https://geny.com/','https://www.geny.com/')}
        if record.get('numero') and not target.get('numero'):
            target['numero']=str(record['numero'])
        if url_course(record.get('course_url')) and record.get('numero'):
            target.update(course_url=record['course_url'],numero=str(record['numero']))
        if record.get('engagement'):target['engagement']=engagement_canonique(record['engagement'])
        if record.get('prochain_essai_utc'):target['prochain_essai_utc']=record['prochain_essai_utc']
        for field in ('source_identifiant','identifiant_externe_non_reconcilie','reconciliation_identite'):
            if record.get(field):target[field]=record[field]
        if record.get('identifiants_sources'):
            target.setdefault('identifiants_sources',{}).update(record['identifiants_sources'])
    for record in records:
        record=qualifier_observation(record)
        ident=str(record.get('id',''))
        if re.fullmatch(r'\d{4,15}',ident):
            merge(by_id.setdefault(ident,{'id':ident,'nom':''}),record)
        elif record.get('nom'):unknown.append(record)
    targets=dict(by_id)
    for record in unknown:
        if record.get('identifiant_externe_non_reconcilie'):
            source,ident=next(iter(record['identifiants_sources'].items()))
            merge(targets.setdefault(source+':'+ident,{'nom':record['nom']}),record)
            continue
        link, _ = index.resoudre(record['nom'])
        if link and link['id'] in targets and not targets[link['id']].get('conflit_identite'):
            merge(targets[link['id']], {**record, 'url_geny': link['url_geny']})
        else:
            # Les contextes non identifiés ne sont pas fusionnés sur le seul nom.
            key=cle_contexte(record)
            merge(targets.setdefault(key,{'nom':record['nom']}),record)
    return targets


def actualiser_inventaire(cache,now):
    """Extension explicite et traçable du lot ; jamais un inventaire glissant."""
    cache=Path(cache)
    # Valider le snapshot et l'état avant d'archiver ou de modifier quoi que ce soit.
    state=preparer(cache,now)
    actualiser_cohortes(cache, state)
    local=inventaire_local(cache,inc.lire(cache/INVENTAIRE))
    ajouter_noms_pmu(cache, local, now)
    additions={k:h for k,h in local.items() if k not in state['chevaux']}
    if additions:
        previous=inc.lire(cache/QUEUE) or state
        revision=state.get('revision_inventaire',1)
        digest=hashlib.sha256(json.dumps(previous,sort_keys=True).encode()).hexdigest()[:16]
        archive=cache/QUEUE.parent/'inventaires'/f"{state['inventaire_id']}-r{revision}-{digest}.json"
        inc.ecrire(archive,previous)
        before=len(state['chevaux']);state['chevaux'].update(additions)
        state['revision_inventaire']=revision+1
        state['inventaire_actualise_utc']=now.isoformat()
        state.setdefault('extensions_inventaire',[]).append({'revision':revision+1,
            'utc':now.isoformat(),'cibles_avant':before,'cibles_ajoutees':len(additions),
            'cibles_apres':len(state['chevaux']),'archive_precedente':str(archive.relative_to(cache)),
            'origines_ajouts': dict(sorted(Counter(origine.split(':')[0]
                for h in additions.values() for origine in set(h.get('origines', []))).items()))})
        state['sync_kpi']='A_REPRENDRE'
        state.pop('termine_utc',None)
        bilan(state)
        inc.ecrire(cache/QUEUE,state)
        state=preparer(cache,now)
    else:state.setdefault('revision_inventaire',1)
    inc.ecrire(cache/QUEUE,state)
    inc.ecrire(cache/QUEUE.parent/'bilan.json',rapport(state))
    return state


def nom_reference(nom):
    return str(nom or '').strip().casefold()


def arrivees_verifiees(cache, now):
    for path in sorted((cache/'arrivees').glob('*.json')):
        if not re.fullmatch(r'\d{4}-\d{2}-\d{2}_R\d+C\d+', path.stem):
            continue
        arrival = inc.lire(path)
        checked = inc.instant(arrival.get('verifie_utc'))
        if arrival.get('source') == 'PMU_API_PARTICIPANTS' and checked and checked <= now and arrival.get('arrivee'):
            yield path, arrival


def profils_passe(cache, race):
    for folder in (QUEUE.parent/'partants_retrouves', Path('partants_actuels')):
        doc = inc.lire(cache/folder/race)
        if doc.get('source') == 'PMU_API_PARTICIPANTS' and doc.get('chevaux'):
            return doc['chevaux']
    return {}


def recuperer_listes_manquantes(cache, now, stop_requested):
    """Compléter trois listes au maximum, uniquement pendant l'extension manuelle."""
    from .auto_v18 import BASE, get_json
    from .partants_actuels_v21 import extraire_partants

    missing = []
    for path, arrival in arrivees_verifiees(cache, now):
        profiles = profils_passe(cache, path.name)
        if not profiles or any(h.get('statut_np') not in ('PARTANT', 'NON_PARTANT') for h in profiles.values()):
            missing.append((path, arrival))
    for path, arrival in missing[:3]:
        if stop_requested():
            break
        day, race = path.stem.split('_')
        meeting, number = race.split('C')
        url = f"{BASE}{datetime.fromisoformat(day):%d%m%Y}/{meeting}/C{number}/participants"
        try:
            horses = extraire_partants(get_json(url, timeout=8))
            ranked = {int(h['numero']) for h in arrival['arrivee']}
        except (OSError, ValueError, RuntimeError, TypeError, KeyError) as error:
            print(f'LISTE_PMU_DIFFEREE {path.stem} {type(error).__name__}', flush=True)
            break
        confirmed = {n for n, h in horses.items() if h.get('statut_np') == 'PARTANT' and h.get('nom')}
        if not ranked or not ranked <= confirmed or any(
                h.get('statut_np') not in ('PARTANT', 'NON_PARTANT') or not h.get('nom') for h in horses.values()):
            print(f'LISTE_PMU_INCOHERENTE {path.stem}', flush=True)
            continue
        inc.ecrire(cache/QUEUE.parent/'partants_retrouves'/path.name, {
            'source': 'PMU_API_PARTICIPANTS', 'source_url': url,
            'capture_utc': datetime.now(inc.UTC).isoformat(), 'chevaux': horses})
        print(f'LISTE_PMU_RECUPEREE {path.stem} {len(confirmed)}', flush=True)


def courses_passees(cache, now):
    """Liste des partants confirmés, une ligne par nom et preuves par course."""
    names = {}
    sans_liste = 0
    courses = 0
    inconnus = 0
    for path, arrival in arrivees_verifiees(cache, now):
        courses += 1
        horses = profils_passe(cache, path.name)
        if not horses:
            sans_liste += 1
            continue
        ranked = {str(h['numero']) for h in arrival['arrivee']}
        for number, horse in horses.items():
            key = nom_reference(horse.get('nom'))
            status = horse.get('statut_np')
            if status == 'NON_PARTANT' and str(number) not in ranked:
                continue
            if not key or status == 'NON_PARTANT' or (status != 'PARTANT' and str(number) not in ranked):
                inconnus += 1
                continue
            entry = names.setdefault(key, {'nom': horse['nom'], 'courses': {}})
            entry['courses'].setdefault(path.stem, []).append(number)
    return {'courses_avec_arrivee': courses, 'courses_sans_liste_partants': sans_liste,
            'participations_a_confirmer': inconnus, 'noms': names}


def ajouter_noms_pmu(cache, targets, now):
    """Conserver la graphie PMU si une graphie différente est déjà dans le stock."""
    existing = {nom_reference(h.get('nom')) for h in targets.values()}
    for name, entry in courses_passees(cache, now)['noms'].items():
        if name in existing:
            continue
        contexts = []
        for race, numbers in entry['courses'].items():
            cid = inc.course_geny_connue(cache, race)
            url = ('https://www.geny.com/course/'+cid[5:]+'/partants-pronostics'
                   if re.fullmatch(r'GENY-\d+', str(cid)) else '')
            contexts.extend((not bool(url), race, number, url) for number in numbers)
        _, race, number, url = min(contexts)
        key = 'nom-pmu:'+hashlib.sha256(name.encode()).hexdigest()[:24]
        targets[key] = {'nom': entry['nom'], 'engagement': race, 'numero': number,
                        'course_url': url, 'nom_reference_pmu': True, 'origines': ['PMU:'+race]}


def preparer_noms_passes(cache, state, now):
    inventory = courses_passees(cache, now)
    targets = {}
    for key, horse in state['chevaux'].items():
        horse.pop('autre_contexte_meme_nom', None)
        horse.pop('nom_passe_en_conflit', None)
        horse.pop('partant_course_passee', None)
        targets.setdefault(nom_reference(horse.get('nom')), []).append((key, horse))
    for name, entry in inventory['noms'].items():
        group = targets.get(name, [])
        if not group:
            entry['etat'] = 'ABSENT_DE_LA_FILE'
            continue
        for _, horse in group:
            horse['partant_course_passee'] = True
        ids = {h['id'] for _, h in group if h.get('id')}
        if (len(ids) > 1 or any(h.get('conflit_identite') or h.get('identifiant_externe_non_reconcilie')
                                for _, h in group)
                or any(len(numbers) > 1 for numbers in entry['courses'].values())):
            entry['etat'] = 'IDENTITE_A_VERIFIER'
            for _, horse in group:
                if not horse.get('geny') and not (horse.get('course_url') and horse.get('numero')):
                    horse['nom_passe_en_conflit'] = True
            continue
        eligible = [(key, h) for key, h in group if not h.get('cible_equivalente_a')] or group
        key, primary = min(eligible, key=lambda item: (
            not bool(item[1].get('historique_complet_au_utc')),
            item[1].get('collecte') in ('LIEN_GENY_A_RESOUDRE', 'IDENTITE_A_VERIFIER'),
            not bool(item[1].get('geny')), not bool(item[1].get('id')), item[0]))
        for other, horse in group:
            if other != key:
                horse['autre_contexte_meme_nom'] = key
            retry = inc.instant(horse.get('prochain_essai_utc'))
            if retry and retry > now and retry > (inc.instant(primary.get('prochain_essai_utc')) or now):
                primary['prochain_essai_utc'] = retry.isoformat()
        entry['cible'] = key
        entry['etat'] = ('COMPLET' if primary.get('rattrapage_complet_au_utc') and primary.get('sync') == 'OK'
                         else 'SYNCHRONISATION_A_REPRENDRE' if primary.get('historique_complet_au_utc')
                         else primary.get('collecte', 'A_REPRENDRE'))
        if entry['etat'] == 'COMPLET' and primary.get('ferrures_manquantes'):
            entry['etat'] = 'FERRURES_A_COMPLETER'
    inventory['bilan'] = dict(sorted(Counter(h['etat'] for h in inventory['noms'].values()).items()))
    inventory['noms_distincts'] = len(inventory['noms'])
    inventory['controle_utc'] = now.isoformat()
    state['courses_passees_par_nom'] = {k: v for k, v in inventory.items() if k != 'noms'}
    inc.ecrire(cache/QUEUE.parent/'courses_passees_par_nom.json', inventory)


def preparer(cache,now):
    cache=Path(cache)
    sheets=inc.lire(cache/INVENTAIRE)
    if not sheets.get('capture_utc') or not isinstance(sheets.get('chevaux'),list):
        raise ValueError('INVENTAIRE_SHEETS_REQUIS')
    state=inc.lire(cache/QUEUE)
    if state and (state.get('version')!=1 or not isinstance(state.get('chevaux'),dict)):
        raise ValueError('FILE_RATTRAPAGE_INCOMPATIBLE')
    from .identites_chevaux import IndexGeny
    index = IndexGeny(cache, observations=sheets['chevaux'])
    local = inventaire_local(cache, sheets, index=index)
    if not state:
        targets = {key: dict(horse) for key, horse in local.items()}
        ajouter_noms_pmu(cache, targets, now)
        if not targets:raise ValueError('INVENTAIRE_VIDE')
        state={'version':1,'mode':'RATTRAPAGE_GLOBAL','inventaire_utc':now.isoformat(),
            'inventaire_id':hashlib.sha256((now.isoformat()+'\n'+'\n'.join(sorted(targets))).encode()).hexdigest()[:24],
            'chevaux':targets,'sync_kpi':'A_REPRENDRE','revision_inventaire':1,
            'lignes_historique_initiales':sheets.get('lignes_historique')}
    actualiser_cohortes(cache, state)
    local=inventaire_local(cache,sheets)
    state['dernier_controle_inventaire']={k:sheets.get(k) for k in ('capture_utc','lignes_historique','controle')}
    # Le dénominateur est figé. La production peut néanmoins avoir complété une cible.
    corrections = {}
    for entry in local.values():
        for ident in entry.get('identifiants_sources', {}).values():
            if entry.get('reconciliation_identite') or entry.get('identifiant_externe_non_reconcilie'):
                corrections.setdefault((nom_normalise(entry.get('nom')), ident), []).append(entry)
    # Un autre contexte de course ne doit pas contourner le délai du même cheval.
    production=inc.lire(cache/inc.QUEUE,{'chevaux':{}})['chevaux']
    retries={}
    for h in production.values():
        retry=inc.instant(h.get('prochain_essai_utc'))
        name=nom_normalise(h.get('nom'))
        if retry and name:retries[name]=max(retries.get(name,retry),retry)

    @lru_cache(maxsize=None)
    def capture(ident):
        return inc.capture_valide(cache, ident) if ident else None

    from .ferrures_geny import manquantes
    from .preparation_prochaines import evaluer
    future=evaluer(cache,now)['engagements']
    state['noms_partants_proteges']=sorted({nom_normalise(h['nom']) for h in future})
    covered=set(sheets.get('ids_couverts',[]))
    observed_numbers={}
    for row in sheets['chevaux']:
        context=contexte_verifiable(row)
        if context:observed_numbers.setdefault(context[:2],set()).add(context[2])
    pmu_partants = {}
    for key,h in state['chevaux'].items():
        name = nom_normalise(h.get('nom'))
        possible = corrections.get((name, h.get('id') or h.get('identifiant_historique_original')), [])
        unresolved = [v for v in possible if v.get('identifiant_externe_non_reconcilie') and h.get('id')]
        if unresolved:
            h['identifiant_historique_original']=h.pop('id')
            h.update(identifiant_externe_non_reconcilie=True,
                     identifiants_sources=unresolved[0]['identifiants_sources'])
            for field in ('geny','lien_candidat','historique_complet_au_utc','rattrapage_complet_au_utc'):
                h.pop(field,None)
        # Migration d'un ancien ID non qualifié : le snapshot conserve maintenant
        # son URL source et le registre exige une correspondance vérifiée.
        matches = [v for v in possible if v.get('reconciliation_identite')]
        if len(matches)==1 and h.get('id')!=matches[0]['id'] and not h.get('conflit_identite'):
            fresh=matches[0]
            h.setdefault('identifiant_historique_original',h.get('id'))
            h.update(id=fresh['id'],geny=fresh['geny'],
                     identifiants_sources=fresh['identifiants_sources'],
                     reconciliation_identite=fresh['reconciliation_identite'],
                     priorite_identite_corrigee=True,sync='SANS_MODIFICATION',erreur='')
            h.pop('identifiant_externe_non_reconcilie',None)
            for field in ('historique_complet_au_utc','rattrapage_complet_au_utc','prochain_essai_utc','lien_candidat'):
                h.pop(field,None)
        canonical=engagement_canonique(h.get('engagement'))
        if canonical and canonical!=h.get('engagement'):
            h.setdefault('engagement_source',h['engagement']);h['engagement']=canonical
        if not h.get('numero'):
            numbers=observed_numbers.get((nom_normalise(h.get('nom')),canonical),set())
            if len(numbers)==1:
                h['numero']=next(iter(numbers));h['numero_reconcilie_depuis_snapshot']=True
        h.setdefault('sync','SANS_MODIFICATION')
        cached = capture(h.get('id'))
        h['ferrures_manquantes']=manquantes(cached) if cached else 0
        cached_stamp=inc.instant(cached.get('extrait_utc')) if cached else None
        trusted=bool(cached_stamp and cached_stamp<=now and h.get('nom') and not h.get('conflit_identite')
                     and url_cheval(cached.get('source_url'),h.get('id',''))
                     and str(cached.get('identifiant_cheval',h.get('id')))==h.get('id'))
        if (inc.instant(h.get('rattrapage_complet_au_utc'))==cached_stamp and trusted
                and not h['ferrures_manquantes']):
            if h.get('sync')=='OK':
                h['erreur']='';h.pop('prochain_essai_utc',None)
            continue
        if not trusted:
            h.pop('historique_complet_au_utc',None)
            h.pop('rattrapage_complet_au_utc',None)
        if not h.get('id') and contexte_verifiable(h):
            if canonical not in pmu_partants:
                pmu_partants[canonical] = inc.lire(cache/'partants_actuels'/f'{canonical}.json').get('chevaux', {})
            runner = pmu_partants[canonical].get(str(h['numero']), {})
            if nom_normalise(runner.get('nom')) == name and str(runner.get('age_ans', '')).isdigit():
                h['annee_naissance_pmu'] = int(canonical[:4]) - int(runner['age_ans'])
        if not h.get('id') and not h.get('identifiant_externe_non_reconcilie') and not h.get('conflit_identite'):
            source = re.search(r'/course/(\d+)', str(h.get('course_url') or ''))
            pmu_numbers = [number for number, runner in pmu_partants.get(canonical, {}).items()
                           if nom_normalise(runner.get('nom')) == name]
            duplicate = len(set(pmu_numbers) | observed_numbers.get((name, canonical), set())) > 1
            link, method = index.resoudre(h.get('nom'), 'GENY-'+source[1] if source else None,
                                          h.get('numero'), nom_repris=duplicate, annee=h.get('annee_naissance_pmu'))
            if link:
                h.update(id=link['id'], geny=link, preuve_identite=link['preuve'])
            h['rapprochement_geny'] = method
        # Les preuves de nom sont globales. Les coordonnées de course restent
        # celles du contexte d'origine pour le comptage et les homonymes.
        fresh = local.get(key) or local.get(cle_contexte(h)) or local.get(h.get('id')) or {}
        if nom_normalise(fresh.get('nom')) == name:
            for field in ('geny', 'conflit_identite', 'identifiant_externe_non_reconcilie',
                          'identifiants_sources', 'reconciliation_identite'):
                if fresh.get(field) and not h.get(field):
                    h[field] = fresh[field]
            if not h.get('course_url') and contexte_verifiable(h) == contexte_verifiable(fresh):
                h['course_url'] = fresh.get('course_url', '')
            if fresh.get('engagement'):
                h['engagement_prioritaire'] = fresh['engagement']
        h['recherche_geny_par_nom'] = not bool(h.get('id')) and bool(name)
        if h.get('geny') or url_course(h.get('course_url')) and h.get('numero'):
            h.pop('lien_candidat',None)
        ident=h.get('id','');doc=capture(ident)
        h['ferrures_manquantes']=manquantes(doc) if doc else 0
        stamp=inc.instant(doc.get('extrait_utc')) if doc else None
        if h.get('conflit_identite') or h.get('identifiant_externe_non_reconcilie') or not h.get('nom'):
            h.update(collecte='IDENTITE_A_VERIFIER',motif_actualisation='IDENTITE_A_VERIFIER')
            continue
        if doc and url_cheval(doc.get('source_url'),ident):
            h['geny']={'id':ident,'nom':h['nom'],
                       'url_geny':doc['source_url'].replace('https://geny.com/','https://www.geny.com/')}
        if (stamp and stamp<=now and h.get('geny') and url_cheval(doc.get('source_url'),ident)
                and str(doc.get('identifiant_cheval',ident))==ident):
            h.update(collecte='COMPLET',nombre_performances=len(doc['performances']),
                     historique_complet_au_utc=stamp.isoformat(),motif_actualisation='')
            if ident in covered or not doc['performances']:
                h.update(sync='OK',rattrapage_complet_au_utc=stamp.isoformat(),
                         preuve_sync='INVENTAIRE_SHEETS_CONTROLE',complete_depuis_sauvegarde=True)
                h['erreur']=''
            else:h['sync']='A_FAIRE'
        else:
            h.update(collecte='A_REPRENDRE',motif_actualisation='HISTORIQUE_ABSENT_PARTIEL_OU_NON_DATE')
            if ident and not h.get('geny') and not h.get('course_url'):
                h['lien_candidat']='https://www.geny.com/cheval/'+ident
            if not h.get('geny') and not (url_course(h.get('course_url')) and h.get('numero')):
                if not h.get('lien_candidat'):h['collecte']='LIEN_GENY_A_RESOUDRE'
        if h['ferrures_manquantes']:
            h['motif_actualisation']='FERRURES_HISTORIQUES_A_COMPLETER'
    deadlines = {}
    for h in state['chevaux'].values():
        task = cle_travail_geny(h)
        retry = inc.instant(h.get('prochain_essai_utc'))
        if retry and retry > now:
            deadlines[task] = max(deadlines.get(task, retry), retry)
    for h in state['chevaux'].values():
        applicable = (retries.get(nom_normalise(h.get('nom'))), deadlines.get(cle_travail_geny(h)))
        retry = max((stamp for stamp in applicable if stamp), default=None)
        own = inc.instant(h.get('prochain_essai_utc'))
        if h.get('motif_actualisation') and retry and retry > now and (not own or retry > own):
            h['prochain_essai_utc'] = retry.isoformat()
    groups={}
    for key,h in state['chevaux'].items():
        h.pop('cible_equivalente_a',None)
        context=contexte_verifiable(h)
        if context and not h.get('nom_reference_pmu'):groups.setdefault(context,[]).append(key)
    for keys in groups.values():
        if len(keys)<2:continue
        members=[state['chevaux'][k] for k in keys]
        if len({h['id'] for h in members if h.get('id')})>1:continue
        primary=min(keys,key=lambda k:(not bool(state['chevaux'][k].get('rattrapage_complet_au_utc')),
                                       not bool(state['chevaux'][k].get('geny')),k))
        for key in keys:
            if key!=primary:state['chevaux'][key]['cible_equivalente_a']=primary
        if state['chevaux'][primary].get('rattrapage_complet_au_utc') and state['chevaux'][primary].get('sync')=='OK':
            propager_preuve(state,state['chevaux'][primary])
    preparer_noms_passes(cache, state, now)
    fields = ('contextes_distincts_sans_identifiant', 'noms_distincts_sans_identifiant',
              'identifiants_sans_carriere_complete')
    previous = tuple(state.get('bilan', {}).get(field) for field in fields)
    counts = bilan(state)
    if previous != tuple(counts[field] for field in fields):
        state['sync_kpi'] = 'A_REPRENDRE'
    return state


def cle_travail_geny(horse):
    ident = horse.get('id')
    if ident:
        return ('IDENTIFIANT', ident)
    name = nom_normalise(horse.get('nom'))
    if horse.get('rapprochement_geny') == 'NOM_AMBIGU':
        year = horse.get('annee_naissance_pmu')
        return ('HOMONYME', name, year or contexte_verifiable(horse))
    return ('NOM', name)


def prochaine_tache(state,now,attempts):
    # Une publication en échec est reprise sans nouvelle consultation Geny.
    for key,h in state['chevaux'].items():
        if h.get('cible_equivalente_a') or h.get('autre_contexte_meme_nom') or h.get('nom_passe_en_conflit'):continue
        if h.get('sync')=='A_FAIRE' and attempts.get(('SYNC',key),0)<1:
            retry=inc.instant(h.get('prochaine_sync_utc'))
            if not retry or retry<=now:return key,'SYNC'
    cooldown=inc.instant(state.get('prochain_acces_geny_utc'))
    if cooldown and cooldown>now:return None,'COOLDOWN'
    candidates=[]
    protected=set(state.get('noms_partants_proteges',[]))
    for key,h in state['chevaux'].items():
        if h.get('cible_equivalente_a') or h.get('autre_contexte_meme_nom') or h.get('nom_passe_en_conflit'):continue
        if nom_normalise(h.get('nom')) in protected:continue
        if (h.get('rattrapage_complet_au_utc') and not h.get('ferrures_manquantes')) or not h.get('motif_actualisation'):continue
        if h.get('collecte') == 'IDENTITE_A_VERIFIER':continue
        if h.get('collecte') == 'LIEN_GENY_A_RESOUDRE' and not h.get('recherche_geny_par_nom'):continue
        if h.get('rapprochement_geny') == 'NOM_AMBIGU' and not (h.get('course_url') and h.get('numero')):continue
        retry=inc.instant(h.get('prochain_essai_utc'))
        if attempts.get(('COLLECTE',key),0) or retry and retry>now:continue
        if attempts.get(cle_travail_geny(h)):continue
        priority=0 if h.get('geny') else 1 if h.get('course_url') else 2
        night=inc.priorite_engagement(h,now,manquant=True) if inc.nuit_collecte(now) else 0
        # Une carrière absente/partielle passe avant une carrière déjà complète
        # à enrichir, même si cette dernière dispose d'un lien déjà vérifié.
        enrichment=h.get('motif_actualisation')=='FERRURES_HISTORIQUES_A_COMPLETER'
        # À urgence égale, terminer les carrières des identifiants connus avant
        # la résolution des seuls noms/contextes. Le candidat reste à vérifier.
        unidentified=not bool(h.get('id'))
        corrected=bool(h.get('priorite_identite_corrigee') and not h.get('historique_complet_au_utc'))
        # Le besoin J+1 doit primer sur une identite corrigee ancienne pendant la nuit.
        if state.get('priorite_collecte') == 'STOCK_NOCTURNE':
            order = (enrichment, unidentified, priority, night, h.get('engagement',''), key)
        else:
            order = (enrichment, night, not h.get('partant_course_passee'), not corrected,
                     unidentified, priority, h.get('engagement',''), key)
        candidates.append((order,key))
    return (min(candidates)[1],'COLLECTE') if candidates else (None,'TERMINE_PASSAGE')


def valider_sync(state,horse):
    stamp=horse.get('historique_complet_au_utc')
    if not inc.instant(stamp):raise ValueError('CAPTURE_NON_DATEE')
    horse.update(rattrapage_complet_au_utc=stamp,motif_actualisation='')
    if horse.get('ferrures_manquantes'):
        horse['motif_actualisation']='FERRURES_HISTORIQUES_A_COMPLETER'
    horse['ajouts_confirmes']=horse.get('ajouts_confirmes',0)+horse.get('sync_details',{}).get('Historique chevaux',{}).get('lignes_ajoutees',0)
    propager_preuve(state,horse)


def propager_identite(state, horse):
    """Enregistrer la preuve sur tous les engagements compatibles du même nom."""
    name = nom_normalise(horse.get('nom'))
    ident = horse.get('id')
    if not name or not ident:
        return
    year = horse.get('geny', {}).get('annee_naissance_pmu')
    if horse.get('rapprochement_geny') == 'NOM_AMBIGU' and not year:
        return
    group = [h for h in state['chevaux'].values() if nom_normalise(h.get('nom')) == name
             and (not year or h.get('annee_naissance_pmu') == year)]
    if any((h.get('id') and h['id'] != ident) or h.get('conflit_identite')
           or h.get('nom_passe_en_conflit') or (not year and h.get('rapprochement_geny') == 'NOM_AMBIGU') for h in group):
        return
    for other in group:
        if not other.get('id') and not other.get('identifiant_externe_non_reconcilie'):
            other.update(id=ident, geny=horse.get('geny', {}),
                         preuve_identite=horse.get('preuve_identite', 'NOM_EXACT_UNIQUE'))


def propager_preuve(state,horse):
    propager_identite(state,horse)
    stamp=horse['rattrapage_complet_au_utc']
    # Les contextes répétés d'une identité désormais vérifiée partagent la preuve.
    for other in state['chevaux'].values():
        if other is horse or other.get('conflit_identite'):continue
        same_context=bool(contexte_verifiable(horse) and contexte_verifiable(horse)==contexte_verifiable(other))
        same_id=other.get('id')==horse['id']
        if (same_id or same_context and not other.get('id')) and nom_normalise(other.get('nom'))==nom_normalise(horse['nom']):
            other.update(rattrapage_complet_au_utc=stamp,sync='OK',motif_actualisation='',
                         id=horse['id'],collecte='COMPLET',geny=horse.get('geny',{}),
                         ferrures_manquantes=horse.get('ferrures_manquantes',0),
                         historique_complet_au_utc=stamp,preuve_sync='MEME_IDENTIFIANT_OU_CONTEXTE_VERIFIE',erreur='')
            if horse.get('ferrures_manquantes'):
                other['motif_actualisation']='FERRURES_HISTORIQUES_A_COMPLETER'
                if horse.get('prochain_essai_utc'):other['prochain_essai_utc']=horse['prochain_essai_utc']
            else:other.pop('prochain_essai_utc',None)


def actualiser_cohortes(cache, state):
    """Relire les clés exactes du lot initial depuis sa première archive."""
    if 'cles_initiales' in state:
        return
    revisions = state.get('extensions_inventaire', [])
    if state.get('revision_inventaire', 1) == 1:
        state['cles_initiales'] = sorted(state['chevaux'])
    elif revisions:
        first = revisions[0]
        if first.get('revision') != 2 or not first.get('archive_precedente'):
            return
        path = cache / first['archive_precedente']
        if (cache / QUEUE.parent / 'inventaires').resolve() not in path.resolve().parents:
            return
        initial = inc.lire(path)
        horses = initial.get('chevaux', {})
        if (initial.get('inventaire_id') == state['inventaire_id']
                and len(horses) == first['cibles_avant']
                and horses.keys() <= state['chevaux'].keys()):
            state['cles_initiales'] = sorted(horses)


def bornes_cohortes(state):
    initial = state.get('cles_initiales')
    if initial is None:
        return {}
    initial = set(initial)
    if not initial <= state['chevaux'].keys():
        return {}
    result = {}
    for name, keys in (('initiale', initial), ('extensions', state['chevaux'].keys() - initial)):
        horses = [state['chevaux'][key] for key in keys]
        result[name] = {
            'cibles': len(horses),
            'identifiees': sum(bool(h.get('id')) for h in horses),
            'partielles': sum(h.get('collecte') == 'PARTIEL_HISTORIQUE' for h in horses),
            'completes': sum(bool(h.get('historique_complet_au_utc')) for h in horses),
            'publiees': sum(bool(h.get('rattrapage_complet_au_utc')) and h.get('sync') == 'OK' for h in horses),
        }
    return result


def bilan_lot_96(state):
    reference = inc.lire(Path(__file__).with_name('rattrapage_lot_96.json'))
    if reference.get('inventaire_id') != state.get('inventaire_id'):
        return None
    identities = reference['identifiants_origine']
    by_id = {}
    for horse in state['chevaux'].values():
        by_id.setdefault(horse.get('id'), []).append(horse)
    published = complete = partial = unresolved = 0
    for ident in identities:
        original = state['chevaux'].get(ident, {})
        actual = original.get('id')
        reconciliation = original.get('reconciliation_identite') or {}
        source_ids = reconciliation.get('identifiants') or {}
        if (actual and actual != ident and source_ids.get('geny') == actual
                and ident in source_ids.values() and reconciliation.get('verification_utc')):
            ident = actual
        rows = by_id.get(ident, [])
        published += any(h.get('rattrapage_complet_au_utc') and h.get('sync') == 'OK' for h in rows)
        complete += any(h.get('historique_complet_au_utc') for h in rows)
        partial += any(h.get('collecte') == 'PARTIEL_HISTORIQUE' for h in rows) and not any(
            h.get('historique_complet_au_utc') for h in rows)
        unresolved += not rows
    return {'checkpoint': reference['checkpoint'], 'cibles': len(identities), 'completes': complete,
            'partielles': partial, 'publiees': published, 'restantes': len(identities) - published,
            'sans_correspondance': unresolved}


def persister_etat(cache, state):
    inc.ecrire(cache / QUEUE, state)
    inc.ecrire(cache / QUEUE.parent / 'bilan.json', rapport(state))


def bilan(state):
    horses=list(state['chevaux'].values())
    distinct=[h for h in horses if not h.get('cible_equivalente_a')]
    missing=[h for h in distinct if not h.get('rattrapage_complet_au_utc')]
    unresolved = [h for h in distinct if not h.get('id')]
    named = {nom_normalise(h.get('nom')) for h in unresolved} - {''}
    known = {h['id'] for h in horses if h.get('id')}
    complete_ids = {h['id'] for h in horses if h.get('id') and h.get('historique_complet_au_utc')}
    causes = Counter(
        'SOURCE_EXTERNE_NON_RECONCILIEE' if h.get('identifiant_externe_non_reconcilie') else
        'NOM_AMBIGU' if h.get('conflit_identite') or h.get('rapprochement_geny') == 'NOM_AMBIGU' else
        'NOM_ABSENT' if not nom_normalise(h.get('nom')) else
        'ACCES_LIMITE_429' if h.get('dernier_echec_collecte', {}).get('statut') == 'ACCES_LIMITE_429' else
        'ACCES_REFUSE_403' if h.get('dernier_echec_collecte', {}).get('statut') == 'ACCES_REFUSE_403' else
        'RECHERCHE_SANS_NOM_EXACT' if 'RECHERCHE_GENY_SANS_NOM_EXACT' in h.get('dernier_echec_collecte', {}).get('erreur', '') else
        'AUCUNE_PREUVE_LOCALE_AVEC_COURSE' if h.get('course_url') else
        'AUCUNE_PREUVE_LOCALE_SANS_COURSE'
        for h in unresolved
    )
    state['causes_contextes_sans_geny'] = dict(sorted(causes.items()))
    complete=sum(bool(h.get('rattrapage_complet_au_utc')) and h.get('sync')=='OK' for h in horses)
    previous=state.get('bilan',{})
    state['bilan']={'cibles_inventoriees':len(horses),'cibles_completees':complete,
        'cibles_restantes':len(horses)-complete,
        'cibles_equivalentes':sum(bool(h.get('cible_equivalente_a')) for h in horses),
        'travaux_distincts_restants':sum(not h.get('cible_equivalente_a') and (not h.get('rattrapage_complet_au_utc') or bool(h.get('ferrures_manquantes'))) for h in horses),
        'historiques_ferrures_a_completer':sum(not h.get('cible_equivalente_a') and bool(h.get('ferrures_manquantes')) for h in horses),
        'carrieres_distinctes_a_completer':len(missing),
        'identifiants_sans_carriere_complete':len(known - complete_ids),
        'contextes_distincts_sans_identifiant':len(unresolved),
        'noms_distincts_sans_identifiant':len(named),
        'identifiants_geny_distincts':len(known),
        'identites_non_resolues':sum(not h.get('id') for h in horses),
        'liens_a_resoudre':sum(h.get('collecte')=='LIEN_GENY_A_RESOUDRE' for h in horses),
        'identites_a_verifier':sum(h.get('collecte')=='IDENTITE_A_VERIFIER' for h in horses),
        'synchronisations_en_attente':sum(h.get('sync')=='A_FAIRE' for h in horses),
        'ajouts_confirmes':sum(h.get('ajouts_confirmes',0) for h in horses),
        'tentatives_collecte':previous.get('tentatives_collecte',0),
        'captures_validees':previous.get('captures_validees',0),
        'captures_partielles':previous.get('captures_partielles',0),
        'collectes_rejetees':previous.get('collectes_rejetees',0)}
    state['statut']='TERMINE' if complete==len(horses) and state.get('sync_kpi')=='OK' and not state['bilan']['historiques_ferrures_a_completer'] else 'PARTIEL_REPRENABLE'
    state['phase_reprise']=('CARRIERES_MANQUANTES' if missing else
        'ENRICHISSEMENTS_FERRURES' if state['bilan']['historiques_ferrures_a_completer'] else
        'TERMINE' if state['statut']=='TERMINE' else 'VALIDATION_FINALE')
    if state['statut']!='TERMINE':state.pop('termine_utc',None)
    if state['statut']=='TERMINE' and not state.get('termine_utc'):
        state['termine_utc']=datetime.now(inc.UTC).isoformat()
    return state['bilan']


def rapport(state):
    keys=('version','mode','inventaire_id','inventaire_utc','revision_inventaire','inventaire_actualise_utc',
          'extensions_inventaire','causes_contextes_sans_geny','phase_reprise','derniere_revalidation','passage_utc','maj_utc','statut','priorite_collecte',
          'termine_utc','sync_kpi','bilan','collecte_cycle','motif_fin_passage','lignes_historique_initiales','dernier_controle_inventaire','courses_passees_par_nom')
    report={k:state[k] for k in keys if k in state}
    report['cohortes'] = bornes_cohortes(state)
    lot = bilan_lot_96(state)
    if lot:
        report['lot_96'] = lot
    for key in ('collecte_tentee_utc', 'controle_ordonnancement_utc', 'sync_kpi_utc',
                'dernier_creneau_reserve_utc', 'creneau_reserve'):
        if key in state:
            report[key] = state[key]
    proofs=[]
    for horse in state['chevaux'].values():
        control=horse.get('sync_details',{}).get('Historique chevaux',{}).get('controle',{})
        stamp=horse.get('sync_utc') or control.get('controle_utc')
        if control.get('statut')=='VALIDE' and inc.instant(stamp):
            proofs.append((inc.instant(stamp),{'sync_utc':stamp,**control}))
    if proofs:report['derniere_ecriture_controlee']=max(proofs,key=lambda item:item[0])[1]
    return report


def priorite_production(paths=None):
    """Céder entre deux chevaux si un workflow de production attend le verrou."""
    if os.getenv('GITHUB_ACTIONS')!='true':return None
    repo=os.environ.get('GITHUB_REPOSITORY','')
    token=os.environ.get('GH_TOKEN','')
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+',repo) or not token:
        return 'PRIORITE_PRODUCTION_NON_VERIFIABLE'
    import requests
    try:
        if paths is None:
            paths = {'.github/workflows/pmu-v16.yml', '.github/workflows/historiques-incrementaux.yml'}
        for status in ('pending', 'queued'):
            params = {'status': status, 'per_page': 100}
            if status == 'queued':
                # Les entrées queued anciennes sans job peuvent survivre aux runs suivants.
                # Les runs pending attendent le verrou et restent prioritaires quel que soit leur âge.
                since = datetime.now(inc.UTC) - timedelta(days=1)
                params['created'] = '>=' + since.isoformat(timespec='seconds')
            response = requests.get(f'https://api.github.com/repos/{repo}/actions/runs',
                params=params,
                headers={'Authorization': 'Bearer ' + token, 'Accept': 'application/vnd.github+json'},
                timeout=5)
            response.raise_for_status()
            runs = response.json()['workflow_runs']
            if any(run.get('path', '').split('@', 1)[0] in paths for run in runs):
                return 'PRIORITE_PRODUCTION_EN_ATTENTE'
            if len(runs) == 100:
                return 'PRIORITE_PRODUCTION_NON_VERIFIABLE'
    except Exception:
        return 'PRIORITE_PRODUCTION_NON_VERIFIABLE'
    return None


def synchroniser_kpi(engine, state, cache):
    from .kpi_registre import KPI_TAB

    details = engine.synchroniser_kpi()
    if KPI_TAB not in details:
        raise ValueError('KPI_SHEETS_NON_VERIFIES')
    state.update(sync_kpi='OK', sync_kpi_details=details,
                 sync_kpi_utc=datetime.now(inc.UTC).isoformat())
    bilan(state)
    persister_etat(cache, state)
    inc.checkpoint_distant(cache, queue=QUEUE)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--cache',default='cache_pmu')
    parser.add_argument('--max-minutes',type=int,default=10)
    parser.add_argument('--max-chevaux',type=int)
    parser.add_argument('--publier',action='store_true')
    parser.add_argument('--nocturne',action='store_true')
    parser.add_argument('--actualiser-inventaire',action='store_true')
    parser.add_argument('--archives-diagnostics',default='')
    parser.add_argument('--reconcilier-identites',action='store_true')
    args=parser.parse_args()
    if not 1<=args.max_minutes<=15 or (args.max_chevaux is not None and args.max_chevaux < 1):parser.error('Bornes positives, duree maximale 15 minutes')
    cache=Path(args.cache)
    if args.publier:
        if not all(os.environ.get(k) for k in ('GOOGLE_SHEETS_ID','GOOGLE_SHEETS_SERVICE_ACCOUNT_JSON')):
            raise SystemExit('Secrets Sheets absents : aucune collecte lancee')
        from .preparation_prochaines import autoriser_fond
        from .echeances_production import besoin_pmu, motif_pause_collecte_nocturne
        from .moteur_sheets import SynchroniseurSheets
        if args.nocturne and inc.lire(cache / QUEUE).get('statut') == 'TERMINE':
            print('RATTRAPAGE_DEJA_TERMINE', flush=True)
            return
        verifier_echeances = motif_pause_collecte_nocturne if args.nocturne else besoin_pmu
        def controle_pmu():
            # Le workflow courant traite déjà la collecte incrémentale avant ce passage.
            workflows = {'.github/workflows/pmu-v16.yml'} if args.nocturne else None
            return priorite_production(workflows) or verifier_echeances(cache, datetime.now(inc.UTC))

        def controle_fond():
            return controle_pmu() or autoriser_fond(cache,datetime.now(inc.UTC), reserve=not args.nocturne,
                nocturne=args.nocturne, diagnostic=Path('resultats/rattrapage/ordonnancement_fond.json'))

        def differer(reason, state):
            if state.get('chevaux'):
                now = datetime.now(inc.UTC)
                actualiser_cohortes(cache, state)
                state.update(motif_fin_passage=reason, maj_utc=now.isoformat(),
                             controle_ordonnancement_utc=now.isoformat())
                persister_etat(cache, state)
                inc.checkpoint_distant(cache, queue=QUEUE)
                # Le statut Geny ne doit pas empêcher la reprise d'une publication KPI.
                if state.get('sync_kpi') == 'A_REPRENDRE' and not controle_pmu():
                    engine = SynchroniseurSheets(cache, os.environ['GOOGLE_SHEETS_ID'])
                    try:
                        synchroniser_kpi(engine, state, cache)
                    finally:
                        engine.fermer()
            print('RATTRAPAGE_FOND_DIFFERE '+reason, flush=True)

        reason = controle_pmu() if args.actualiser_inventaire else controle_fond()
        if reason and not (args.reconcilier_identites or args.archives_diagnostics):
            state = inc.lire(cache / QUEUE)
            # Réconciliation locale sous le verrou partagé, même si le budget
            # Geny est réservé aux engagements. Céder si le cycle PMU attend.
            if state.get('chevaux') and (cache/INVENTAIRE).exists() and not controle_pmu():
                now = datetime.now(inc.UTC)
                state = preparer(cache, now)
                # Une capture déjà persistée peut être publiée sans consulter Geny.
                # Les échéances PMU et le verrou de production restent prioritaires.
                if (reason in ('COOLDOWN_GENY_GLOBAL', 'PARTANT_PRIORITAIRE_DISPONIBLE',
                               'REPRISE_PARTANT_PRIORITAIRE_IMMINENTE')
                        and prochaine_tache(state, now, {})[1] == 'SYNC'):
                    inc.run(cache, max_minutes=args.max_minutes, max_chevaux=0,
                            publier=True, mode='rattrapage', stop_requested=controle_pmu)
                    return
            differer(reason, state)
            return
        engine=SynchroniseurSheets(cache,os.environ['GOOGLE_SHEETS_ID'])
        try:
            if args.reconcilier_identites:
                from .reconcilier_identites_sheets import reparer
                reparer(engine)
            inc.ecrire(cache/INVENTAIRE,engine.inventaire_rattrapage())
        finally:engine.fermer()
        if args.actualiser_inventaire:
            recuperer_listes_manquantes(cache, datetime.now(inc.UTC), controle_pmu)
            state = actualiser_inventaire(cache, datetime.now(inc.UTC))
            reason = controle_fond()
            if reason:
                print('INVENTAIRE_COURSES_PASSEES_PERSISTE '+json.dumps(
                    state['courses_passees_par_nom'], ensure_ascii=False), flush=True)
                differer(reason, state)
                return
        if args.archives_diagnostics:
            from .revalider_diagnostics import revalider_artifacts
            revalider_artifacts(cache,args.archives_diagnostics)
        if args.nocturne:
            from .resolution_identites_courses import PILOTE, passage

            if inc.lire(cache/PILOTE).get('statut') != 'TERMINE':
                now = datetime.now(inc.UTC)
                state = preparer(cache, now)
                if prochaine_tache(state, now, {})[1] != 'SYNC':
                    def checkpoint_identites():
                        persister_etat(cache, state)
                        inc.checkpoint_distant(cache, queue=QUEUE)

                    if passage(cache, state, stop_requested=controle_fond, checkpoint=checkpoint_identites):
                        return
        max_chevaux = args.max_chevaux if args.nocturne else 1
        state=inc.run(cache,max_minutes=args.max_minutes,max_chevaux=max_chevaux,
                      publier=True,mode='rattrapage',nocturne=args.nocturne,
                      stop_requested=controle_fond,
                      creneau_reserve=lambda: inc.lire(Path('resultats/rattrapage/ordonnancement_fond.json')).get('creneau_reserve'))
    else:
        state=(actualiser_inventaire if args.actualiser_inventaire else preparer)(cache,datetime.now(inc.UTC))
    print('BILAN_RATTRAPAGE '+json.dumps({'statut':state['statut'],'inventaire_id':state['inventaire_id'],
                                       'revision_inventaire':state.get('revision_inventaire',1),'courses_passees_par_nom':state.get('courses_passees_par_nom'),'phase_reprise':state['phase_reprise'],
                                       'motif_fin_passage':state.get('motif_fin_passage','BUDGET_OU_FILE_EPUISE'),
                                       'collecte_cycle':state.get('collecte_cycle'), **state['bilan']},ensure_ascii=False),flush=True)


if __name__=='__main__':main()
