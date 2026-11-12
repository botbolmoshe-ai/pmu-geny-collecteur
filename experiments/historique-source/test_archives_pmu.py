"""Premier rapprochement historique PMU sur dates passees, en lecture seule.
Une ligne historique n'est validee que si cheval, date passee et classement sont presents.
Echantillon volontairement restreint aux R1C1 des 21 jours precedents.
"""
import datetime,json,time
from urllib.request import Request,urlopen
from urllib.error import HTTPError,URLError
BASE="https://online.turfinfo.api.pmu.fr/rest/client/1/programme/"
TODAY=datetime.date(2026,11,12)
def get(url):
 try:
  with urlopen(Request(url,headers={"User-Agent":"Mozilla/5.0","Accept":"application/json"}),timeout=12) as r:return r.status,json.load(r)
 except HTTPError as e:return e.code,None
 except (URLError,TimeoutError,OSError,ValueError):return None,None
def main():
 status,source=get(BASE+"12112026/R1/C1/participants")
 target=[h for h in (source or {}).get("participants",[])[:3] if h.get("idCheval")]
 found=[];errors=[];checked=0
 for days in range(1,22):
  day=TODAY-datetime.timedelta(days=days)
  date=day.strftime("%d%m%Y")
  url=BASE+date+"/R1/C1/participants"
  code,root=get(url);checked+=1
  if code!=200 or not isinstance(root,dict):errors.append({"date":day.isoformat(),"http":code});continue
  for horse in root.get("participants",[]):
   for target_horse in target:
    if horse.get("idCheval")!=target_horse["idCheval"]:continue
    rank=horse.get("ordreArrivee")
    if isinstance(rank,bool) or not isinstance(rank,int) or rank<1:continue
    found.append({"cheval":horse.get("nom"),"idCheval":horse["idCheval"],"date":day.isoformat(),"course":"R1C1","classement":rank,"driver":horse.get("driver"),"entraineur":horse.get("entraineur"),"ferrure":horse.get("deferre"),"url_source":url})
  time.sleep(.15)
 matched=len(set(x["idCheval"] for x in found))
 print(json.dumps({"source":"pmu","type":"HISTORIQUE_RECONSTRUIT_PAR_COURSES","chevaux_cibles":[h.get("nom") for h in target],"dates_testees":checked,"courses_testees":checked,"chevaux_avec_historique":matched,"performances_historiques_validees":len(found),"taux_couverture_chevaux":round(matched/len(target),3) if target else None,"taux_completude_historique":None,"performances":found,"erreurs":errors,"limite":"R1C1 uniquement; ne mesure pas la completude de l'historique total"},ensure_ascii=False))
if __name__=="__main__":main()
