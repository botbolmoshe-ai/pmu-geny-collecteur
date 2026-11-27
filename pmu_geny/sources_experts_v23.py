"""Collecte avant départ : PMU seul ; identités et provenance.

Pas d'inférence de pronostic à partir des cotes, des notes ou de l'ordre HTML.
Les parseurs ne lisent que les blocs de la course attestée, jamais ses références.
Les parseurs Equidia/ZEturf restent lisibles pour les archives, sans accès réseau.
"""
from __future__ import annotations
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse, urljoin
from urllib.request import Request, urlopen
from bs4 import BeautifulSoup
from .ml_v19 import load, save
from .liaison_chevaux_v22 import nom_normalise

SOURCES = ('pmu',)
HOSTS = {'online.turfinfo.api.pmu.fr'}

def text(node):
    return ' '.join(node.get_text(' ', strip=True).split()) if node else ''

def track(value):
    value=nom_normalise(value).lower()
    for prefix in ('hippodromedeparis', 'hippodromedes', 'hippodromedu', 'hippodromede', 'hippodromed', 'paris'):
        if value.startswith(prefix):return value[len(prefix):]
    return value

def title(value):
    value=re.sub(r'\s*\([^)]*\)\s*$','',str(value or ''))
    value=nom_normalise(value).lower()
    return value[4:] if value.startswith('prix') else value

def same_race(course, date, hippodrome, name):
    return (date==course['date'] and bool(title(name)) and
            title(name)==title(course.get('nom','')) and
            bool(track(hippodrome)) and track(hippodrome)==track(course.get('hippodrome','')))

def fetch_public(url):
    parsed=urlparse(url)
    if parsed.scheme!='https' or parsed.hostname not in HOSTS:raise ValueError('HOTE_NON_AUTORISE')
    req=Request(url,headers={'User-Agent':'Mozilla/5.0 (compatible; PMU-Trot-Research/1.0)'})
    with urlopen(req,timeout=10) as response:
        if urlparse(response.url).hostname not in HOSTS:raise ValueError('REDIRECTION_EXTERNE')
        body=response.read(3_000_001)
        if len(body)>3_000_000:raise ValueError('PAGE_TROP_VOLUMINEUSE')
    return body.decode('utf-8','replace')

def number(value):
    try:
        n=int(value)
        return n if 1<=n<=40 else None
    except (ValueError,TypeError):return None

def matched(participants, num, name):
    return bool(num and nom_normalise(name) and nom_normalise(name)==nom_normalise(participants.get(str(num),{}).get('nom','')))

def ferrure_label(value):
    from .ferrures_geny import libelle_ferrure
    return libelle_ferrure(value)

def profile_equidia(p):
    from .partants_actuels_v21 import age_valide, sexe_normalise, gains_valides
    horse=p.get('cheval') or {}
    fields={'age_ans':age_valide(p.get('age_cheval',horse.get('age_cheval'))),
            'sexe':sexe_normalise(p.get('sexe_cheval',horse.get('sexe_cheval'))),
            'gains_euros':gains_valides(p.get('gains_carriere',horse.get('gains_carriere'))),
            'driver_jockey':(p.get('monte') or {}).get('nom_monte'),
            'entraineur':(p.get('entraineur') or {}).get('nom_entraineur'),
            'musique':p.get('musique',horse.get('musique'))}
    return {k:v for k,v in fields.items() if v is not None and v!=''}

def parser_equidia(html, course, participants, code=None):
    soup=BeautifulSoup(html,'html.parser')
    state=soup.find('script',id='serverApp-state')
    if not state:raise ValueError('EQUiDIA_STRUCTURE_ABSENTE')
    data=json.loads(state.string or state.get_text())
    rc=code or course['code']
    r,c=rc.split('C')
    key=f"courses/{course['date']}/{r}/C{c}"
    race=data.get('v2/'+key,{})
    reunion=race.get('reunion') or {}
    if not same_race(course,reunion.get('date_reunion'),reunion.get('lib_reunion',''),race.get('liblong_prix_course','')):
        raise ValueError('COURSE_NON_CORRESPONDANTE')
    answers={}
    for p in race.get('partants',[]):
        n=number(p.get('num_partant'));name=(p.get('cheval') or {}).get('nom_cheval','')
        if not matched(participants,n,name):continue
        item={'nom':name,'profil':profile_equidia(p)}
        if p.get('libelle_avis_entraineur'):item['avis_entraineur']=p['libelle_avis_entraineur']
        answers[str(n)]=item
    interviews=data.get(key+'/interview',{}) or {}
    for interview in interviews.get('interview_partants',[]):
        p=interview.get('partant') or {}
        n=number(p.get('num_partant'));name=(p.get('cheval') or {}).get('nom_cheval','')
        if matched(participants,n,name) and str(n) in answers and interview.get('texte'):
            answers[str(n)]['interview']={'auteur':interview.get('personne',''),'texte':interview['texte']}
    # La ferrure textuelle est publiée dans le tableau ; aucun code numérique supposé.
    for row in soup.select('table.course-result-table tr'):
        name=text(row.select_one('.name-cheval'))
        for item in answers.values():
            if nom_normalise(item['nom'])==nom_normalise(name):
                icon=row.select_one('svg[aria-label]')
                ferr=ferrure_label(icon.get('aria-label','')) if icon else ''
                if ferr:item['profil']['ferrure']=ferr
    prono=data.get(key+'/pronostic',{}) or {}
    ranking=[]
    if prono.get('status')=='published':
        for p in prono.get('pronostic_analyses',[]):
            n=number(p.get('num_partant'));name=(p.get('cheval') or {}).get('nom_cheval','')
            if not matched(participants,n,name) or str(n) not in answers:continue
            item=answers[str(n)]
            if p.get('analysis_horse'):item['commentaire']=p['analysis_horse']
            rank=number(p.get('position'))
            if rank:ranking.append((rank,n))
        # Publier uniquement un ordre explicitement donné, sans doublon de rang.
    ordered=[n for rank,n in sorted(ranking)] if len({r for r,n in ranking})==len(ranking) else []
    creator=prono.get('creator') or {}
    return {'chevaux':answers,'pronostic':ordered,
            'auteur':' '.join(str(creator.get(k,'')) for k in ('firstname','lastname')).strip(),
            'publication':prono.get('published_at',''),
            'parametres':{k:race[k] for k in ('discipline','distance','lib_parcours_course','categ_course','type_course','conditions_txt_course','montant_total_allocation') if race.get(k) is not None}}

def links(html, pattern):
    soup=BeautifulSoup(html,'html.parser')
    return sorted({urlparse(a['href']).path for a in soup.select('a[href]')
                   if not urlparse(a['href']).netloc and re.fullmatch(pattern,urlparse(a['href']).path)})

def parser_zeturf(html, course, participants):
    soup=BeautifulSoup(html,'html.parser')
    heading=soup.select_one('h1.nom-course');name=text(soup.select_one('h2.nom-course'))
    date=datetime.fromisoformat(course['date']).strftime('%d/%m/%Y')
    if not heading or date not in text(heading) or not same_race(course,course['date'],text(heading.select_one('.hippodrome')),name):
        raise ValueError('COURSE_NON_CORRESPONDANTE')
    from .partants_actuels_v21 import sexe_normalise
    answers={}
    for row in soup.select('table.table-runners tr[data-runner]'):
        n=number(row.get('data-runner'));a=row.select_one('a.horse-name')
        # Le libellé accessible contient parfois la ferrure : texte direct seulement.
        horse=' '.join(a.find_all(string=True,recursive=False)).strip() if a else ''
        horse=re.sub(r'\s*\(NP\)\s*$','',horse,flags=re.I).strip()
        if not matched(participants,n,horse):continue
        profile={}
        sa=re.fullmatch(r'([MHF])/(\d{1,2})',text(row.select_one('.sexe-age')))
        if sa and 2<=int(sa[2])<=25:profile.update(age_ans=int(sa[2]),sexe=sexe_normalise(sa[1]))
        record=row.select_one('td.record')
        rec=' '.join(record.find_all(string=True,recursive=False)) if record else ''
        gains=re.search(r'(\d[\d\s\u202f\u00a0]*)\s*€',rec)
        if gains:profile['gains_euros']=int(re.sub(r'\s','',gains[1]))
        ferr=ferrure_label(text(row.select_one('[id^=deferres-][role=tooltip]')))
        if ferr:profile['ferrure']=ferr
        item={'nom':horse,'profil':profile}
        comment=text(row.select_one('td.info .score-ia-hidden'))
        if comment:item['commentaire']=comment
        opinion=text(row.select_one('[id^=avis-entraineur-][role=tooltip]'))
        if opinion:item['avis_entraineur']=opinion
        answers[str(n)]=item
    ordered=[number(text(x)) for x in soup.select('.prono-cards .numero-cheval-card')]
    if any(str(n) not in answers for n in ordered) or len(set(ordered))!=len(ordered):ordered=[]
    return {'chevaux':answers,'pronostic':ordered,
            'auteur':text(soup.select_one('#analyse-zeturf .pronostiqueur')),
            'commentaire_course':text(soup.select_one('#analyse-zeturf .pronostic')),
            'parametres':{'conditions_txt_course':text(soup.select_one('.conditions'))}}

def parser_pmu(prono, course, participants):
    from dashboard.trot_analytics.dates import PARIS
    stamp=prono.get('dateReunion')
    date=datetime.fromtimestamp(stamp/1000,PARIS).date().isoformat() if isinstance(stamp,(int,float)) else ''
    if (date!=course['date'] or f"R{prono.get('numeroReunion')}C{prono.get('numeroCourse')}"!=course['code']):
        raise ValueError('COURSE_NON_CORRESPONDANTE')
    answers={};ranking=[]
    for p in prono.get('selection',[]):
        n=number(p.get('num_partant'))
        # L'API lie le numéro à l'identifiant date/hippodrome/course/partant.
        ident=str(p.get('id_nav_partant',''))
        expected=course['date'].replace('-','')
        c=course['code'].split('C')[1]
        if not n or str(n) not in participants or not re.fullmatch(expected+r'-[A-Z0-9]+-'+c+'-'+str(n),ident):continue
        answers[str(n)]={'nom':participants[str(n)]['nom'],'commentaire':p.get('commentaire','')}
        rank=number(p.get('rang'))
        if rank:ranking.append((rank,n))
    ordered=[n for r,n in sorted(ranking)] if len({r for r,n in ranking})==len(ranking) else []
    return {'chevaux':answers,'pronostic':ordered,'auteur':prono.get('signature',''),
            'fournisseur':prono.get('source',''),'parametres':{}}

def collecter(cache, course, raw, now=None, fetch=None):
    from .partants_actuels_v21 import extraire_partants
    clock=(lambda:now) if now is not None else (lambda:datetime.now(timezone.utc))
    started=clock();departure=datetime.fromisoformat(course['depart'])
    if started>=departure:return 'APRES_DEPART'
    fetch=fetch or fetch_public
    cache=Path(cache);path=cache/'avis_experts'/f"{course['date']}_{course['code']}.json"
    old=load(path,{}) or {}
    participants={str(n):p for n,p in extraire_partants(raw).items()}
    # Les anciens avis Zone-Turf/Geny ne sont jamais requalifiés comme nouvelles sources.
    results={};sources={};pages=cache/'avis_experts'/'pages_v23'
    def page(url):
        ident=hashlib.sha256(url.encode()).hexdigest()
        file=pages/(ident+'.json');prior=load(file,{}) or {}
        try:fresh=(started-datetime.fromisoformat(prior['capture_utc'])).total_seconds()<3600
        except (ValueError,KeyError):fresh=False
        if fresh:
            if prior.get('erreur'):raise RuntimeError(prior['erreur'])
            return prior['html'],prior['capture_utc']
        try:
            html=fetch(url)
            capture=clock().isoformat()
            save(file,{'url':url,'capture_utc':capture,'html':html})
            return html,capture
        except Exception as exc:
            save(file,{'url':url,'capture_utc':clock().isoformat(),'erreur':type(exc).__name__})
            raise
    r,c=course['code'].split('C')
    day=datetime.fromisoformat(course['date']).strftime('%d%m%Y')
    pmu_url=f'https://online.turfinfo.api.pmu.fr/rest/client/1/programme/{day}/{r}/C{c}/pronostics'
    for source in SOURCES:
        url=pmu_url
        try:
            try:
                html,capture=page(url);doc=parser_pmu(json.loads(html),course,participants)
            except Exception as exc:
                capture=clock().isoformat()
                doc={'chevaux':{},'pronostic':[],'erreur_pronostic':type(exc).__name__,'parametres':{}}
            doc['parametres']={**course.get('parametres_pmu',{}),**{k:course[k] for k in ('discipline','distance_m','depart','nom','hippodrome') if course.get(k) is not None}}
            for n,p in participants.items():
                doc['chevaux'].setdefault(n,{'nom':p.get('nom','')})['profil']=p
            if clock()>=departure:raise ValueError('COLLECTE_APRES_DEPART')
            sources[source]={**doc,'url':url,'capture_utc':capture,
                             'statut':'RECUPERE' if doc['chevaux'] else 'AUCUN_PARTANT_ASSOCIE',
                             'statut_pronostic':'PUBLIE' if doc['pronostic'] else 'NON_PUBLIE_OU_NON_ACCESSIBLE',
                             'partants_associes':len(doc['chevaux']),'partants_attendus':len(participants)}
        except Exception as exc:
            sources[source]={'url':url,'statut':'INDISPONIBLE','erreur':f'{type(exc).__name__}: {str(exc)[:120]}',
                             'controle_utc':clock().isoformat(),'statut_pronostic':'NON_VERIFIE'}
            # Préserver seulement les relevés de cette version, nom entier identique.
            prior=(old.get('sources') or {}).get(source,{})
            if old.get('version')==23 and prior.get('chevaux') and datetime.fromisoformat(prior['capture_utc'])<departure:
                sources[source]={**prior,'dernier_controle':sources[source]}
    for source,doc in sources.items():
        doc['pronostic']=[n for n in doc.get('pronostic',[]) if matched(participants,number(n),doc.get('chevaux',{}).get(str(n),{}).get('nom',''))]
        for n,item in doc.get('chevaux',{}).items():
            if not matched(participants,number(n),item.get('nom','')):continue
            out=results.setdefault(n,{'nom':item['nom']})
            out['avis_'+source]=item.get('commentaire') or item.get('avis_entraineur','')
            out['profil_'+source]=item.get('profil',{})
            out[source+'_source']=doc['url'];out[source+'_collecte_utc']=doc['capture_utc']
    if clock()>=departure:return 'APRES_DEPART'
    save(path,{'version':23,'date':course['date'],'course':course['code'],
               'capture_utc':clock().isoformat(),'sources':sources,'chevaux':results,
               'avis_identiques':[],'politique_sources':'PMU_SEUL',
               'regle':'Avant départ; identité attestée; caractéristiques et avis PMU uniquement'})
    completer_partants(cache,course)
    print(f"EXPERTS_SOURCES {course['date']} {course['code']} "+' | '.join(s.upper()+':'+str(d.get('partants_associes',0))+'/'+str(len(participants))+' prono='+d.get('statut_pronostic','NON_VERIFIE') for s,d in sources.items()),flush=True)
    return 'EXPERTS_'+str(sum(s.get('statut')=='RECUPERE' for s in sources.values()))+'_SUR_'+str(len(SOURCES))

def completer_partants(cache,course):
    """Conserver les profils PMU ; retirer les anciens compléments tiers."""
    from .partants_actuels_v21 import profil_pmu_exclusif
    cache=Path(cache);path=cache/'partants_actuels'/f"{course['date']}_{course['code']}.json"
    current=load(path,{}) or {}
    if not current.get('chevaux'):return
    current['chevaux']={n:profil_pmu_exclusif(actual) for n,actual in current['chevaux'].items()}
    save(path,current)

def champs_sheet(experts,n,nom=None):
    """Champs PMU exclusivement ; les anciennes sources tierces sont ignorées."""
    out={};item=(experts.get('chevaux') or {}).get(str(n),{})
    sources=experts.get('sources',{}) if experts.get('version')==23 else {}
    if nom is not None and nom_normalise(nom)!=nom_normalise(item.get('nom','')):item={}
    for source in SOURCES:
        doc=sources.get(source,{})
        out['avis_'+source]=item.get('avis_'+source,'') if sources else ''
        out['prono_'+source]=', '.join(map(str,doc.get('pronostic',[])))
        out['source_'+source]=(doc.get('url','')+' · '+doc.get('capture_utc','')).strip(' ·')
    out['couverture_experts']=' | '.join(s.upper()+': '+sources.get(s,{}).get('statut','NON_VERIFIE')+(' (dernier contrôle en échec)' if sources.get(s,{}).get('dernier_controle') else '')+' / prono '+sources.get(s,{}).get('statut_pronostic','NON_VERIFIE') for s in SOURCES)
    out['divergences_sources']=''
    out['synthese_actualite']=' | '.join(s.upper()+': '+out['avis_'+s] for s in SOURCES if out['avis_'+s])
    params=sources.get('pmu',{}).get('parametres',{})
    out['conditions_course']=params.get('conditions','') if isinstance(params.get('conditions',''),str) else ''
    return out
