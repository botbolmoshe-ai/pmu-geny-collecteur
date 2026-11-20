"""Ferrures Geny : données structurées et libellés accessibles des performances."""
from __future__ import annotations

import json
import re
import unicodedata
from collections import defaultdict
from datetime import datetime
from bs4 import BeautifulSoup
from .departs_trot import depart_historique_geny
from .echeances_production import PARIS, instant

CODES={'FF':'F','DD':'D4','DF':'DA','FD':'DP','PP':'P4','PF':'PA','FP':'PP',
       'PD':'DP/PA','DP':'DA/PP'}
FERRURES=set(CODES.values())


def normaliser(value):
    value=unicodedata.normalize('NFKD',str(value or '')).upper()
    return ''.join(c for c in value if c.isalnum() and not unicodedata.combining(c))


def libelle_ferrure(value):
    key=normaliser(value)
    if key.endswith('PIEDS'):key=key[:-5]
    if key=='NONDEFERRE':return 'F'
    if key in ('FERRE','FERRESDES4','FERREDES4','FERREDESQUATRE','FERREDESQUATREPIEDS'):return 'F'
    if key in ('DEFERREDES4','DEFERREDESQUATRE','DEFERREDESQUATREPIEDS'):return 'D4'
    if key in ('PLAQUEDES4','PLAQUEDESQUATRE','PROTEGEDES4','PROTEGEDESQUATRE'):return 'P4'
    da=bool(re.search(r'DEFERRE(?:DES)?(?:ANTERIEURS|ANT)',key))
    dp=bool(re.search(r'DEFERRE(?:DES)?(?:POSTERIEURS|POST)',key))
    pa=bool(re.search(r'(?:PLAQUE|PROTEGE)(?:DES)?(?:ANTERIEURS|ANT)',key))
    pp=bool(re.search(r'(?:PLAQUE|PROTEGE)(?:DES)?(?:POSTERIEURS|POST)',key))
    if da and dp:return 'D4'
    if pa and pp:return 'P4'
    if pa and dp:return 'DP/PA'
    if da and pp:return 'DA/PP'
    return 'DA' if da else 'DP' if dp else 'PA' if pa else 'PP' if pp else ''


def flux_next(html):
    """Assembler les fragments de données Next.js sans exécuter de JavaScript."""
    soup=BeautifulSoup(html,'html.parser');chunks=[];decoder=json.JSONDecoder()
    for script in soup.find_all('script'):
        raw=script.string or script.get_text()
        for match in re.finditer(r'self\.__next_f\.push\(',raw):
            try:payload,_=decoder.raw_decode(raw[match.end():].lstrip())
            except ValueError:continue
            if isinstance(payload,list) and len(payload)>1 and isinstance(payload[1],str):chunks.append(payload[1])
    return ''.join(chunks)


def documents(html):
    # Les enregistrements texte Flight sont préfixés par leur longueur UTF-8.
    # Un document JSON peut commencer juste après ce texte, sans saut de ligne.
    flux = flux_next(html).encode('utf-8', errors='replace')
    header = re.compile(rb'[0-9a-fA-F]+:')
    sized = re.compile(rb'[TAOoUSsLlGgMmV]([0-9a-fA-F]+),')
    position = 0
    while position < len(flux):
        marker = header.match(flux, position)
        if marker:
            start = marker.end()
            frame = sized.match(flux, start)
            if frame:
                position = frame.end() + int(frame[1], 16)
                continue
        end = flux.find(b'\n', position)
        if end == -1:
            end = len(flux)
        position = end + 1
        if marker:
            try:
                yield json.loads(flux[start:end])
            except ValueError:
                continue


def participations(html,ident):
    found={}
    def walk(value):
        if isinstance(value,dict):
            horse=value.get('cheval')
            if (isinstance(horse,dict) and str(horse.get('id'))==str(ident)
                    and isinstance(value.get('course'),dict)
                    and ('deferre' in value or depart_historique_geny(value['course'], value))):
                key=(value.get('id'), value['course'].get('id'), value.get('deferre'),
                     value['course'].get('depart'), str(value.get('positionDepart')))
                found[key]=value
            for item in value.values():walk(item)
        elif isinstance(value,list):
            for item in value:walk(item)
    for document in documents(html):walk(document)
    return list(found.values())


def cle_performance(row):
    return (str(row.get('date','')),normaliser(row.get('hippodrome')),normaliser(row.get('discipline')),
            str(row.get('distance_m','')).replace(' ',''))


def observations(html,ident):
    result=defaultdict(list)
    for item in participations(html,ident):
        # La déclaration de la course ouverte sur la page n'est pas une
        # performance passée, même si le cheval a déjà couru le même jour.
        if not item.get('rang') and not item.get('incident'):continue
        code=CODES.get(item.get('deferre'))
        course=item['course'];distance=course.get('distance');recul=item.get('recul') or 0
        if not isinstance(distance,int) or not isinstance(recul,int):continue
        hip=item.get('hippodrome') or (item.get('reunion') or {}).get('hippodrome') or {}
        row={'date':str(course.get('dateHeureCourse',''))[:10],'hippodrome':hip.get('nom',''),
             'discipline':{'ATTELE':'Attelé','MONTE':'Monté'}.get(course.get('specialite'),''),
             'distance_m':str(distance+recul),'classement':str(item.get('rang') or ''),
             'chrono':str(item.get('redKm') or '')}
        departure = depart_historique_geny(course, item)
        when_raw = course.get('dateHeureCourse')
        when = instant(when_raw)
        if not when and hip.get('nationaliteIso') == 'FR':
            try:
                when = datetime.fromisoformat(when_raw).replace(tzinfo=PARIS)
            except (TypeError, ValueError):
                pass
        if (code or departure) and all(cle_performance(row)):
            result[cle_performance(row)].append({'ferrure':code,'code_brut':item.get('deferre'),
                'depart_trot':departure, 'source':'GENY_DONNEES_STRUCTUREES',
                'course_id':course.get('id'), 'depart_course':when,**row})
    # Les performances chargées au défilement ne sont pas toujours dans le bloc
    # initial Next.js. Leurs attributs aria-label restent dans le DOM final.
    soup=BeautifulSoup(html,'html.parser');verified=False
    for script in soup.select('script[type="application/ld+json"]'):
        try:data=json.loads(script.string or script.get_text())
        except ValueError:continue
        if isinstance(data,dict) and str(data.get('identifier'))==str(ident):verified=True
    if not verified:return result
    heading=next((x for x in soup.find_all(string=True) if str(x).strip()=='CARRIÈRE'),None)
    if heading is None:return result
    from .collecte_geny_v4 import DATE_RE,parse_career
    container=None
    for parent in heading.parents:
        text=parent.get_text(' | ',strip=True)
        if 'Trier par' in text and DATE_RE.search(text):container=parent;break
    if container is None:return result
    seen=set()
    for icon in container.select('[aria-label]'):
        code=libelle_ferrure(icon.get('aria-label'))
        if not code:continue
        for parent in icon.parents:
            text=parent.get_text(' | ',strip=True)
            dates=list(DATE_RE.finditer(text))
            if len(dates)>1:break
            if len(dates)==1 and dates[0].start()==0:
                rows=parse_career('CARRIÈRE\nsur 1 courses',[text])['performances']
                if rows and all(rows[0].get(k) for k in ('date','hippodrome','discipline','distance_m','classement')):
                    row=rows[0];signature=(cle_performance(row),row['classement'],row['chrono'],code)
                    if signature not in seen:
                        result[cle_performance(row)].append({**row,'ferrure':code,
                            'source':'GENY_ARIA_LABEL','code_brut':icon['aria-label']})
                        seen.add(signature)
                    break
            if parent is container:break
    return result


def manquantes(doc):
    return sum(row.get('ferrure') not in FERRURES or row.get('ferrure_qualification')=='CONFLIT'
               for row in doc.get('performances',[]))


def couverture(doc):
    missing=manquantes(doc);total=len(doc.get('performances',[]))
    doc.update(ferrures_renseignees=total-missing,ferrures_manquantes=missing,
               ferrures_statut='COMPLET' if not missing else 'A_COMPLETER',schema_ferrures=1)


def enrichir(doc,html,ident,source_url,capture_utc=None):
    candidates=observations(html,ident);added=0;conflicts=0;departures_added=0
    capture = instant(capture_utc)
    for row in doc.get('performances',[]):
        found=candidates.get(cle_performance(row),[])
        if not found:continue
        # Une même date peut contenir plusieurs courses : ne pas arbitrer des
        # ferrures divergentes. Rang et chrono peuvent confirmer la bonne ligne.
        exact=[x for x in found if normaliser(x.get('classement'))==normaliser(row.get('classement'))
               and normaliser(x.get('chrono'))==normaliser(row.get('chrono'))]
        if exact:
            found = exact
        else:
            # Le contexte seul ne suffit pas à identifier la course.
            codes = {x['ferrure'] for x in found if x.get('ferrure')}
            if len(codes) > 1:
                conflicts += 1
                row['ferrure_qualification'] = 'CONFLIT'
            continue
        departures = [x for x in found if x.get('depart_trot') and x.get('course_id')
                      and capture and x.get('depart_course') and x['depart_course'] < capture]
        if (not row.get('depart_trot') and departures and len({x['course_id'] for x in departures}) == 1
                and all(x['depart_trot'] == departures[0]['depart_trot'] for x in departures)):
            proof = departures[0]
            row['depart_trot'] = {**proof['depart_trot'], 'source':proof['source'],
                                  'url':source_url, 'capture_utc':capture_utc,
                                  'course_id':proof['course_id']}
            departures_added += 1
        found = [x for x in found if x.get('ferrure')]
        if not found:
            continue
        codes={x['ferrure'] for x in found}
        courses = {str(x['course_id']) for x in found if x.get('course_id')}
        if len(codes) != 1 or len(courses) > 1:
            conflicts+=1;row['ferrure_qualification']='CONFLIT';continue
        code=next(iter(codes))
        if row.get('ferrure'):
            if row['ferrure']!=code:
                conflicts+=1;row['ferrure_qualification']='CONFLIT'
            continue
        proof = next((x for x in found if x.get('course_id')), found[0])
        row.update(ferrure=code,ferrure_qualification='SOURCEE',ferrure_source={'source':proof['source'],'url':source_url,
            'capture_utc':capture_utc,'code_brut':proof['code_brut'],'identifiant_cheval':str(ident),
            'courses_ids':sorted(courses)})
        added+=1
    couverture(doc)
    return {'ferrures_ajoutees':added,'departs_ajoutes':departures_added,
            'conflits':conflicts,'ferrures_manquantes':doc['ferrures_manquantes']}
