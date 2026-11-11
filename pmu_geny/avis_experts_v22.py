"""Avis experts capturés avant départ, jamais reconstitués a posteriori.

Sources actuellement intégrées: champs explicitement publiés par l'API PMU et
avis éditorial du Quinté Zone-Turf. Aucun avis inventé si page refusée, si
appariement non exact, ou si la course n'est pas celle du Quinté.
"""
from __future__ import annotations
import json
import re
import unicodedata
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.request import Request, urlopen
from .ml_v19 import load, save
from .liaison_chevaux_v22 import nom_normalise

WEEKDAYS=('lundi','mardi','mercredi','jeudi','vendredi','samedi','dimanche')
MONTHS=('janvier','fevrier','mars','avril','mai','juin','juillet','aout','septembre','octobre','novembre','decembre')
POSITIVE={'positif':'POSITIF','positive':'POSITIF','neutre':'NEUTRE',
          'negatif':'NEGATIF','négatif':'NEGATIF'}

def url_quinte(day):
    date=datetime.fromisoformat(day).date()
    return ('https://www.zone-turf.fr/quinte/'+WEEKDAYS[date.weekday()]+
            '-'+str(date.day)+'-'+MONTHS[date.month-1]+'-'+str(date.year)+'/')

def _fetch_zone(url):
    if not url.startswith('https://www.zone-turf.fr/quinte/'):raise ValueError('Adresse Zone-Turf non valide')
    req=Request(url,headers={'User-Agent':'Mozilla/5.0 (compatible; PMU-Trot-Research/1.0)','Accept':'text/html'})
    with urlopen(req,timeout=9) as reply:
        if reply.status!=200:raise RuntimeError(f'ZONE_TURF_HTTP_{reply.status}')
        data=reply.read(1_200_001)
        if len(data)>1_200_000:raise ValueError('Page Zone-Turf trop volumineuse')
    return data.decode('utf-8','replace')

class TableRows(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.rows=[];self.active=False;self.in_td=False;self.row=[];self.cell=[]
    def handle_starttag(self,tag,attrs):
        if tag=='tr':
            self.active=True;self.row=[];self.in_td=False
        elif self.active and tag in ('td','th'):
            self.in_td=True;self.cell=[]
        elif self.active and tag=='img':
            vals=dict(attrs)
            alt=vals.get('alt','').strip()
            if alt:self.cell.append(alt)
            description=vals.get('data-impression','').strip()
            if description:self.cell.append('EXPERT_COMMENT:'+description)
    def handle_data(self,data):
        if self.active and self.in_td:self.cell.append(data)
    def handle_endtag(self,tag):
        if self.active and tag in ('td','th'):
            self.row.append(' '.join(' '.join(self.cell).split()))
            self.in_td=False;self.cell=[]
        elif tag=='tr' and self.active:
            if self.row:self.rows.append(self.row)
            self.active=False;self.row=[]

def parser_zone_quinte(html,course,participants):
    """Ne retenir que le Quinté dont hippodrome et nom sont attestés dans la page."""
    visible=re.sub(r'<[^>]+>',' ',html)
    visible=' '.join(visible.split())
    if 'quint' not in nom_normalise(visible[:15000]) and 'tierce' not in nom_normalise(visible[:15000]):
        return {}
    track=nom_normalise(course.get('hippodrome',''))
    track='vincennes' if 'vincennes' in track else 'amiens' if 'amiens' in track else track
    if track and track not in nom_normalise(visible[:15000]):return {}
    title=nom_normalise(course.get('nom',''))
    if title and title not in nom_normalise(visible[:25000]):return {}
    parsed=TableRows();parsed.feed(html)
    answers={}
    for row in parsed.rows:
        if not row or not re.fullmatch(r'\d{1,2}',row[0].strip()):continue
        numero=int(row[0].strip())
        horse=participants.get(str(numero))
        if not horse:continue
        name=nom_normalise(horse.get('nom',''))
        if not name:continue
        # Identité obligatoire: numéro + nom entier normalisé retrouvé dans la ligne.
        row_text=nom_normalise(' '.join(row[1:]))
        if name not in row_text:continue
        opinions=[POSITIVE[token.casefold()] for cell in row for token in
                  re.findall(r'(?i)\b(?:positif|positive|neutre|negatif|négatif)\b',
                             cell.split('EXPERT_COMMENT:')[0])
                  if token.casefold() in POSITIVE]
        if len(set(opinions))==1 and opinions:
            # Thèmes explicitement mentionnés dans les commentaires éditoriaux,
            # reformulés plutôt que reproduits verbatim.
            commentary=' '.join(' '.join(row).split('EXPERT_COMMENT:')[1:])
            content=nom_normalise(commentary)
            themes=[]
            for label,keys in (
                ('aptitude au parcours',('parcours','piste','vincennes')),
                ('forme récente',('forme','victoire','triomph','performan')),
                ('niveau de compétition',('generation','groupe','meilleurs','opposition')),
                ('retour après absence',('absent','rentr','repos','retour')),
                ('régularité',('regulier','regularite','constan')),
                ('déferrage',('deferre','ferrure')),
                ('risque de faute',('faute','disqualif','sagesse'))):
                if any(nom_normalise(k) in content for k in keys):themes.append(label)
            message='Avis '+opinions[0].lower()
            if themes:message+=' — thèmes : '+', '.join(themes[:3])
            answers[str(numero)]=message+' (Zone-Turf)'
    return answers

def _pmu_opinion(item):
    for key in ('commentaireEntraineur','avisEntraineur','commentaireExpert','avisExpert'):
        value=item.get(key)
        if isinstance(value,str) and 8<=len(value.strip())<=350:
            return value.strip()
        if isinstance(value,dict):
            for k in ('commentaire','texte','libelle'):
                val=value.get(k)
                if isinstance(val,str) and 8<=len(val.strip())<=350:return val.strip()
    return ''

def collecter(cache,course,raw,now=None,fetch=None):
    from .auto_v18 import _list,_num
    now=now or datetime.now(timezone.utc)
    if now>=datetime.fromisoformat(course['depart']):return 'APRES_DEPART'
    cache=Path(cache)
    path=cache/'avis_experts'/f"{course['date']}_{course['code']}.json"
    old=load(path,{}) or {}
    rows=_list(raw,'participants','partants')
    names={str(n):{'nom':next((str(x[k]) for k in ('nomCheval','nom','nomParticipant')
                               if isinstance(x.get(k),str) and x[k]),'')}
           for x in rows if isinstance(x,dict)
           for n in [_num(x,'numPmu','num','numero','numeroPmu')] if n is not None}
    results=dict(old.get('chevaux',{}))
    for x in rows:
        if not isinstance(x,dict):continue
        n=_num(x,'numPmu','num','numero','numeroPmu')
        if n is None:continue
        avis=_pmu_opinion(x)
        if avis:
            existing=results.get(str(n),{})
            results[str(n)]={**existing,'avis_pmu':avis,
                              'pmu_collecte_utc':now.isoformat(),
                              'pmu_source':'PMU_API_PARTICIPANTS'}
    url=url_quinte(course['date'])
    # Une page de Quinté ne doit jamais être attribuée à une autre course.
    # Même quand l'URL fonctionne, la correspondance titre/hippodrome est vérifiée.
    previous=old.get('zone_turf_controle_utc','')
    attempt=True
    if previous:
        try:attempt=(now-datetime.fromisoformat(previous)).total_seconds()>=3600
        except ValueError:attempt=True
    status='ZONE_TURF_NON_VERIFIE'
    # Une erreur de parseur corrigée doit pouvoir être retestée dans le même jour.
    if str(old.get('statut_zone_turf','')).startswith('ZONE_TURF_ERREUR_'):
        attempt=True
    if not attempt:
        status=old.get('statut_zone_turf','ZONE_TURF_NON_VERIFIE')
    else:
        try:
            daily=cache/'avis_experts'/'pages'/f"{course['date']}_quinte.html"
            if fetch is None and daily.exists():
                from datetime import timedelta
                age=now-datetime.fromtimestamp(daily.stat().st_mtime,tz=timezone.utc)
                html=daily.read_text(encoding='utf-8') if age<timedelta(hours=1) else _fetch_zone(url)
            else:
                html=(fetch or _fetch_zone)(url)
            if fetch is None:
                daily.parent.mkdir(parents=True,exist_ok=True)
                daily.write_text(html,encoding='utf-8')
            zone=parser_zone_quinte(html,course,names)
            for n,avis in zone.items():
                original=results.get(n,{})
                results[n]={**original,'avis_zone_turf':avis,
                            'zone_collecte_utc':now.isoformat(),
                            'zone_source':url}
            status='ZONE_TURF_AVIS_RECUPERES' if zone else 'ZONE_TURF_AUCUN_AVIS_ASSOCIE'
        except Exception as exc:
            status=f'ZONE_TURF_ERREUR_{type(exc).__name__}'\n            error_detail=str(exc)[:160]
    save(path,{'date':course['date'],'course':course['code'],'capture_utc':now.isoformat(),
               'source_zone_turf':url,'zone_turf_controle_utc':now.isoformat() if attempt else previous,
               'statut_zone_turf':status,'erreur_zone_turf':locals().get('error_detail',''),
               'chevaux':results,
               'regle':'Avis avant départ; noms et numéros exacts; indisponible != avis neutre'})
    return status
