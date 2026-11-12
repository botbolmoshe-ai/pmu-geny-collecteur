"""Test PMU: historiques des partants de R1C7 du 12/11/2026, sans ecriture production.
Recherche par idCheval exact dans les archives de courses des 14 jours precedents.
Chaque performance exige une date anterieure et un classement entier positif.
La couverture mesuree n'est pas une completude de carriere.
"""
import datetime,json,time
from urllib.request import Request,urlopen
from urllib.error import HTTPError,URLError
BASE="https://online.turfinfo.api.pmu.fr/rest/client/1/programme/"
DAY=datetime.date(2026,11,12)
RACE="R1/C7"
def get(url):
 try:
  with urlopen(Request(url,headers={"User-Agent":"Mozilla/5.0","Accept":"application/json"}),timeout=10) as r:return r.status,json.load(r)
 except HTTPError as e:return e.code,None
 except (URLError,TimeoutError,OSError,ValueError):return None,None
def main():
 code,initial=get(BASE+DAY.strftime("%d%m%Y")+"/"+RACE+"/participants")
 horses=[h for h in (initial or {}).get("participants",[]) if h.get("idCheval")]
 ids={h["idCheval"]:h for h in horses}
 out={"source":"pmu","course_cible":"2026-11-12 R1C7","type":"COLLECTE_HISTORIQUE_PAR_ARCHIVES","http_partants":code,"partants_identifies":len(ids),"chevaux_avec_historique":0,"performances_historiques_validees":0,"courses_archives_lues":0,"dates_archives_lues":0,"performances":[],"erreurs":[],"taux_couverture_chevaux":None,"taux_completude_historique":None}
 if not ids:print(json.dumps(out,ensure_ascii=False));return
 for delta in range(1,15):
  day=DAY-datetime.timedelta(days=delta);dt=day.strftime("%d%m%Y")
  status,program=get(BASE+dt)
  if status!=200 or not isinstance(program,dict):out["erreurs"].append({"date":str(day),"http":status,"etape":"programme"});continue
  out["dates_archives_lues"]+=1
  for meeting in program.get("programme",{}).get("reunions",[]):
   pays=meeting.get("pays")
   if isinstance(pays,dict) and pays.get("code") not in (None,"FRA","FR"):continue
   r=meeting.get("numOfficiel")
   for race in meeting.get("courses",[]):
    c=race.get("numOrdre")
    if not isinstance(r,int) or not isinstance(c,int):continue
    if out["courses_archives_lues"]>=500:break
    url=BASE+dt+f"/R{r}/C{c}/participants";status,body=get(url)
    out["courses_archives_lues"]+=1
    if status!=200 or not isinstance(body,dict):out["erreurs"].append({"date":str(day),"course":f"R{r}C{c}","http":status});continue
    for h in body.get("participants",[]):
     ident=h.get("idCheval")
     if ident not in ids:continue
     rank=h.get("ordreArrivee")
     if isinstance(rank,bool) or not isinstance(rank,int) or rank<=0:continue
     out["performances"].append({"cheval":h.get("nom"),"idCheval":ident,"date":str(day),"course":f"R{r}C{c}","classement":rank,"driver":h.get("driver"),"entraineur":h.get("entraineur"),"ferrure":h.get("deferre"),"preuve":url})
    time.sleep(.04)
   if out["courses_archives_lues"]>=500:break
  if out["courses_archives_lues"]>=500:break
 out["performances_historiques_validees"]=len(out["performances"])
 out["chevaux_avec_historique"]=len(set(p["idCheval"] for p in out["performances"]))
 out["taux_couverture_chevaux"]=round(out["chevaux_avec_historique"]/len(ids),3)
 out["limite"]="Fenetre 14 jours, maximum 500 courses; aucune inference sur l'historique total."
 print(json.dumps(out,ensure_ascii=False))
if __name__=="__main__":main()
