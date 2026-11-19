"""Réutiliser les identités déjà observées dans une course, sans ouvrir de fiche."""
from datetime import timedelta
import re
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup

from .ferrures_geny import documents
from .liaison_chevaux_v22 import nom_normalise


def lien_valide(url, ident=None):
    parsed=urlparse(str(url or ''))
    match=re.match(r'^/cheval/(\d{4,15})(?:\D|$)',parsed.path)
    return bool(parsed.scheme=='https' and parsed.hostname in ('geny.com','www.geny.com')
                and match and (not ident or match[1]==str(ident)))


def extraire(rows,html,engagement,source_url,stamp):
    course=re.search(r'/course/(\d+)',source_url)
    parsed=urlparse(source_url)
    if not course or parsed.scheme!='https' or parsed.hostname not in ('geny.com','www.geny.com'):return {}
    candidates={}
    structured={}
    def ajouter(name,ident,url,source):
        if lien_valide(url,ident):
            candidates.setdefault(nom_normalise(name),{}).setdefault(str(ident),{
                'id':str(ident),'nom':name,'url_geny':url,'source_lien':source})
    participants=[]
    for row in rows:
        cells=row.get('cells',[])
        if len(cells)<4 or not re.fullmatch(r'\d{1,2}',str(cells[0])):continue
        if not 1<=int(cells[0])<=30:continue
        number=str(int(cells[0]));name=cells[2].strip()
        participants.append((number,name))
        tds=BeautifulSoup(row.get('html',''),'html.parser').find_all('td',recursive=True)
        if len(tds)<3 or nom_normalise(tds[2].get_text(' ',strip=True))!=nom_normalise(name):continue
        anchor=tds[2].find('a',href=True)
        if anchor:
            url=urljoin(source_url,anchor['href']);match=re.search(r'/cheval/(\d+)',url)
            if match:ajouter(name,match[1],url,'GENY_LIEN_TABLEAU')
    def parcourir(value):
        if isinstance(value,dict):
            key = value.get('queryKey')
            if (isinstance(key, list) and len(key) >= 3 and key[0] == 'course'
                    and str(key[1]) == course[1] and 'withPartants' in key):
                state = value.get('state') or {}
                meeting = state.get('data') or {}
                race = meeting.get('course') or {}
                if (state.get('status') == 'success' and str(race.get('id')) == course[1]
                        and (not engagement or meeting.get('dateReunion') == engagement[:10])):
                    for record in race.get('participants') or []:
                        horse = record.get('cheval') or {}
                        number, ident, name = str(record.get('numero')), str(horse.get('id')), horse.get('nom')
                        if not (re.fullmatch(r'[1-9]\d?', number) and re.fullmatch(r'\d{4,15}', ident)
                                and isinstance(name, str) and nom_normalise(name)):
                            continue
                        slug = horse.get('slug') or ''
                        target = ident + ('-'+slug if re.fullmatch(r'[a-z0-9_-]+', slug) else '')
                        url = f'https://www.geny.com/cheval/{target}/course/{course[1]}'
                        structured.setdefault(number, {})[(nom_normalise(name), ident)] = {
                            'id': ident, 'nom': name, 'url_geny': url, 'source_lien': 'GENY_QUERY_PARTANTS'}
            horse=value.get('cheval');race=value.get('course')
            if (isinstance(horse,dict) and isinstance(race,dict)
                    and str(race.get('id'))==course[1]
                    and isinstance(horse.get('nom'),str)
                    and re.fullmatch(r'\d{4,15}',str(horse.get('id','')))):
                ajouter(horse['nom'],horse['id'],'https://www.geny.com/cheval/'+str(horse['id']),
                        'GENY_DONNEES_STRUCTUREES_COURSE')
            for child in value.values():parcourir(child)
        elif isinstance(value,list):
            for child in value:parcourir(child)
    for doc in documents(html):parcourir(doc)
    names=[nom_normalise(n) for _,n in participants]
    numbers=[n for n,_ in participants]
    horses={}
    for number,name in participants:
        found=candidates.get(nom_normalise(name),{})
        if len(found)==1 and names.count(nom_normalise(name))==1 and numbers.count(number)==1:
            horses[number]={**next(iter(found.values())),'nom':name}
    for number, found in structured.items():
        if len(found) != 1:
            horses.pop(number, None)
            continue
        horse = next(iter(found.values()))
        if number not in horses or horses[number]['id'] == horse['id']:
            horses[number] = horse
        else:
            horses.pop(number)
    return {'engagement':engagement,'source_url':source_url,'course_geny_id':course[1],
            'capture_utc':stamp,'http':200,'chevaux':horses}


def memoriser(cache,horse,out):
    from .historiques_incrementaux import lire,ecrire,instant
    proof=lire(out/'liens_course.json')
    if (not proof or proof.get('http')!=200 or proof.get('engagement')!=horse.get('engagement')
            or proof.get('source_url')!=horse.get('course_url') or not instant(proof.get('capture_utc'))):return
    match=re.search(r'/course/(\d+)',str(horse.get('course_url','')))
    parsed=urlparse(str(horse.get('course_url','')))
    if (not match or proof.get('course_geny_id')!=match[1] or parsed.scheme!='https'
            or parsed.hostname not in ('geny.com','www.geny.com')):return
    own=proof.get('chevaux',{}).get(str(horse.get('numero')),{})
    if nom_normalise(own.get('nom'))!=nom_normalise(horse.get('nom')):return
    if any(not lien_valide(h.get('url_geny'),h.get('id')) for h in proof['chevaux'].values()):return
    ecrire(cache/'sources_geny/liens'/f"{horse['engagement']}.json",proof)


def pour_cheval(cache,engagement,numero,nom,now,course_url):
    from .historiques_incrementaux import lire,instant
    proof=lire(cache/'sources_geny/liens'/f'{engagement}.json')
    stamp=instant(proof.get('capture_utc'))
    course=re.search(r'/course/(\d+)',str(course_url))
    if (proof.get('engagement')!=engagement or proof.get('source_url')!=course_url
            or not course or proof.get('course_geny_id')!=course[1]
            or proof.get('http')!=200 or not stamp or not timedelta(0)<=now-stamp<=timedelta(hours=24)):
        return None
    h=proof.get('chevaux',{}).get(str(numero),{})
    if nom_normalise(h.get('nom'))!=nom_normalise(nom) or not lien_valide(h.get('url_geny'),h.get('id')):
        return None
    return {**h,'preuve_course_utc':proof['capture_utc']}
