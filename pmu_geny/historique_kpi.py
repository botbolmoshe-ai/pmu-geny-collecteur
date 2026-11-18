"""Un relevé de qualité par indicateur et jour d'observation, sans reconstruction."""
from datetime import datetime,timezone
import json
from urllib.parse import quote
from zoneinfo import ZoneInfo

TAB='Historique qualité'
SOURCE_HEADERS=['Dimension','Indicateur','Valeur (automatique)','Définition / réserve','Total de référence (automatique)']
HEADERS=['Clé du relevé','Date du relevé','Relevé UTC',*SOURCE_HEADERS]


def planifier(source,existing,now):
    if now.tzinfo is None:raise ValueError('Releve sans fuseau')
    if not source or source[0][:5]!=SOURCE_HEADERS:raise ValueError('SCHEMA_KPI_INCOMPATIBLE')
    if not any(any(v not in ('',None) for v in row) for row in existing):existing=[]
    if existing and existing[0]!=HEADERS:raise ValueError('SCHEMA_HISTORIQUE_KPI_INCOMPATIBLE')
    day=now.astimezone(ZoneInfo('Europe/Paris')).date().isoformat()
    positions={}
    for n,row in enumerate(existing[1:],2):
        if not any(v not in ('',None) for v in row):continue
        if len(row)<5 or row[0] in positions:raise ValueError('DOUBLON_OU_RELEVE_INVALIDE')
        try:
            stamp=datetime.fromisoformat(row[2])
            if (json.loads(row[0])!=[row[1],row[4]] or stamp.tzinfo is None
                    or stamp.astimezone(ZoneInfo('Europe/Paris')).date().isoformat()!=row[1]):
                raise ValueError('RELEVE_INCOHERENT')
        except (ValueError,TypeError):raise ValueError('RELEVE_INCOHERENT')
        positions[row[0]]=(n,row)
    updates=[];last=max((n for n,row in enumerate(existing,1) if any(v not in ('',None) for v in row)),default=1)
    if not existing:updates.append({'range':f"'{TAB}'!A1:H1",'values':[HEADERS]})
    labels=set()
    for row in source[1:]:
        if len(row)<2 or not str(row[1] or '').strip():continue
        label=str(row[1])
        if label in labels:raise ValueError('INDICATEUR_KPI_EN_DOUBLE')
        labels.add(label)
        key=json.dumps([day,label],ensure_ascii=False,separators=(',',':'))
        record=[key,day,now.astimezone(timezone.utc).isoformat(),*(row+['']*5)[:5]]
        if key in positions:
            n,old=positions[key]
            stamp=datetime.fromisoformat(old[2])
            if stamp.tzinfo is None or stamp>now:raise ValueError('RELEVE_PLUS_RECENT_QUE_CAPTURE')
        else:last+=1;n=last
        if key not in positions or positions[key][1]!=record:
            updates.append({'range':f"'{TAB}'!A{n}:H{n}",'values':[record]})
    return updates,max(last,1)


def enregistrer(engine,tables,now=None):
    from .lectures_sheets import get_lecture
    source_path=quote("'Data Quality & KPI'!A:E",safe="!:'")
    source=engine.check(get_lecture(engine.session,engine.base+'/values/'+source_path,
        params={'valueRenderOption':'UNFORMATTED_VALUE'},timeout=30)).get('values',[])
    now=now or datetime.now(timezone.utc)
    if TAB not in tables:
        engine.check(engine.session.post(engine.base+':batchUpdate',json={'requests':[{'addSheet':{
            'properties':{'title':TAB,'gridProperties':{'rowCount':1000,'columnCount':8}}}}]},timeout=30))
        tables=engine.metadata()
    properties=tables[TAB];count=properties['gridProperties']['rowCount']
    path=quote(f"'{TAB}'!A1:H{count}",safe="!:'")
    existing=engine.check(get_lecture(engine.session,engine.base+'/values/'+path,
        params={'valueRenderOption':'UNFORMATTED_VALUE'},timeout=30)).get('values',[])
    updates,last=planifier(source,existing,now)
    if last>count:
        engine.check(engine.session.post(engine.base+':batchUpdate',json={'requests':[{'appendDimension':{
            'sheetId':properties['sheetId'],'dimension':'ROWS','length':max(last-count,1000)}}]},timeout=30))
    if updates:
        # Ranges explicites : relire puis réessayer ne crée pas un deuxième append.
        engine.check(engine.session.post(engine.base+'/values:batchUpdate',json={
            'valueInputOption':'RAW','data':updates},timeout=45))
    print('HISTORIQUE_KPI '+json.dumps({'date':now.astimezone(ZoneInfo('Europe/Paris')).date().isoformat(),
        'plages_actualisees':len(updates)},ensure_ascii=False),flush=True)
