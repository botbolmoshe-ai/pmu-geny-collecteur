import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from logic import records, selected, number, timestamp, result_matching
from quality import render_quality
from performance import render_performance

st.set_page_config(page_title="TROT Analytics",page_icon="📊",layout="wide")
PARIS=ZoneInfo("Europe/Paris")
TABS=("Courses & Prévisions","Résultats & Analyse","Data Quality & KPI")
HISTORY_TAB="Historique qualité"
SCOPES=["https://www.googleapis.com/auth/spreadsheets.readonly"]

@st.cache_data(ttl=120,show_spinner=False)
def read_registry():
    creds=Credentials.from_service_account_info(dict(st.secrets["google_service_account"]),scopes=SCOPES)
    api=build("sheets","v4",credentials=creds,cache_discovery=False)
    ranges=["'"+t+"'!A1:AZ" for t in TABS]
    metadata=api.spreadsheets().get(spreadsheetId=st.secrets['spreadsheet_id'],fields='sheets(properties(title))').execute(num_retries=2)
    has_history=any(s.get('properties',{}).get('title')==HISTORY_TAB for s in metadata.get('sheets',[]))
    if has_history:ranges.append("'"+HISTORY_TAB+"'!A1:H")
    resp=api.spreadsheets().values().batchGet(spreadsheetId=st.secrets["spreadsheet_id"],
        ranges=ranges,valueRenderOption="UNFORMATTED_VALUE").execute(num_retries=2)
    data=[records(v.get("values",[])) for v in resp.get("valueRanges",[])]
    if len(data)!=len(ranges): raise ValueError("Onglets manquants")
    if not data[0] or "Clé course (technique)" not in data[0][0]: raise ValueError("Schéma courses incompatible")
    return (*data[:3],data[3] if has_history else [],datetime.now(timezone.utc))

st.title("TROT Analytics")
st.caption("Observatoire des courses · France · Lecture seule")
st.caption("Version interface : 2026.11.18.2 · Maturité et validation prospective du ML")
# Fail closed even if a public code repository is used for deployment.
# A separate app password prevents accidental public disclosure.
try:
    import hmac
    expected=str(st.secrets["app_password"])
    if len(expected)<16: raise ValueError("Mot de passe trop court")
except Exception:
    st.warning("Configuration sécurisée requise. Aucun accès aux données.")
    st.stop()
if not st.session_state.get("authenticated"):
    with st.form("auth"):
        supplied=st.text_input("Code d’accès",type="password")
        submitted=st.form_submit_button("Connexion")
    if submitted:
        if hmac.compare_digest(supplied,expected):
            st.session_state.authenticated=True
            st.rerun()
        else: st.error("Accès refusé.")
    st.stop()

toolbar=st.columns(2)
if toolbar[0].button("Actualiser"): read_registry.clear()
if toolbar[1].button("Déconnexion"):
    st.session_state.authenticated=False
    st.rerun()
try:
    with st.spinner("Lecture du registre…"):
        courses,results,kpis,quality_history,loaded=read_registry()
except Exception:
    st.error("Registre inaccessible ou configuration incompatible. Aucune donnée simulée.")
    st.stop()
now=datetime.now(timezone.utc)
st.caption("Registre lu à "+loaded.astimezone(PARIS).strftime("%d/%m/%Y %H:%M:%S")+" · fraîcheur des fiches distincte")
page=st.radio("Navigation",["Accueil","Courses","Résultats","Performance","Qualité"],horizontal=True,label_visibility="collapsed")
if page in ("Accueil","Courses","Résultats"):
    dates=sorted({str(r.get("Date")) for r in courses if r.get("Date")})
    today=now.astimezone(PARIS).date().isoformat()
    day=st.date_input("Date",value=now.astimezone(PARIS).date()).isoformat()
    groups={}
    for row in courses:
        if str(row.get("Date"))==day and row.get("Clé course (technique)"):
            groups.setdefault(row["Clé course (technique)"],[]).append(row)
    groups=dict(sorted(groups.items(),key=lambda kv: str(kv[1][0].get("Départ (Paris)",""))))
    hips=sorted({str(rows[0].get("Hippodrome","")) for rows in groups.values()})
    hip=st.selectbox("Hippodrome",["Tous"]+hips)
    groups={key:rows for key,rows in groups.items() if hip=="Tous" or rows[0].get("Hippodrome")==hip}
    day_results=[r for r in results if str(r.get("Date"))==day and (hip=="Tous" or r.get("Hippodrome")==hip)]
if page=="Accueil":
    cols=st.columns(2)
    cols[0].metric("Courses",len(groups))
    cols[1].metric("TOP3 directs",sum(bool(selected(r,"direct")) for r in groups.values()))
    cols=st.columns(2)
    cols[0].metric("TOP3 ML",sum(bool(selected(r,"ml")) for r in groups.values()))
    total=sum(len(r) for r in groups.values())
    hist=sum((number(h.get("Historique · Nb performances récupérées")) or 0)>0 for r in groups.values() for h in r)
    cols[1].metric("Historiques disponibles",f"{hist}/{total}")
    if total: st.progress(hist/total,text="Couverture des participations")
    if not groups: st.info("Aucune course dans le registre pour ce filtre.")
    st.subheader("Prochains départs")
    upcoming=[r[0] for r in groups.values() if timestamp(r[0].get("Départ (Paris)")) and timestamp(r[0]["Départ (Paris)"])>now]
    if upcoming:
        st.dataframe(pd.DataFrame(upcoming)[["Course R/C","Hippodrome","Départ (Paris)","Discipline"]],hide_index=True,use_container_width=True)
    else: st.caption("Aucun départ futur enregistré pour cette date.")
elif page=="Courses":
    if not groups: st.info("Aucune course pour ce filtre.")
    for key,rows in groups.items():
        first=rows[0]; depart=timestamp(first.get("Départ (Paris)"))
        label=first.get("Course R/C","")+" · "+str(first.get("Hippodrome",""))+" · "+(depart.astimezone(PARIS).strftime("%H:%M") if depart else "heure inconnue")
        with st.expander(label,expanded=len(groups)==1):
            st.caption("Course passée — prévisions archivées" if depart and depart<=now else "Prévisions stockées · non recalculées")
            st.write(first.get("Discipline",""),"·",first.get("Distance (m)",""),"m")
            for method,title in [("direct","TOP3 direct"),("ml","TOP3 ML")]:
                chosen=selected(rows,method)
                if chosen:
                    st.markdown("**"+title+" : "+" — ".join(str(h["N°"]) for h in chosen)+"**")
                    st.caption(" / ".join(str(h.get("Cheval","")) for h in chosen))
                else: st.caption(title+" : sélection indisponible ou non vérifiée")
            st.caption("Calcul direct : "+str(first.get("TOP3 direct · Calcul UTC") or "non renseigné"))
            st.caption("ML : "+str(first.get("ML · État du modèle") or "non renseigné"))
            st.caption("NP : "+", ".join(str(h["N°"]) for h in rows if h.get("Non-partant (NP)")=="NON_PARTANT") if any(h.get("Non-partant (NP)")=="NON_PARTANT" for h in rows) else "Aucun NP enregistré (voir fraîcheur des fiches)")
            columns=["N°","Cheval","Ferrure · Course du jour","Musique PMU","Non-partant (NP)","Historique · Nb performances récupérées","Données actuelles · Mise à jour UTC"]
            st.dataframe(pd.DataFrame(rows).reindex(columns=columns),hide_index=True,use_container_width=True)
elif page=="Résultats":
    st.caption("Matching en % · uniquement sur preuves disponibles. Absence ≠ 0 %. ML non évaluable sans preuve enregistrée.")
    table=[]
    for r in day_results:
        table.append({"Course":r.get("Course R/C"),"Direct":r.get("TOP3 direct · Chevaux"),"ML":r.get("TOP3 ML · Chevaux"),
            "Podium enregistré":r.get("Arrivée · N° officiels"),"Direct (%)":result_matching(r,"direct",now),
            "ML (%)":result_matching(r,"ml",now),"État":r.get("Évaluation · État"),"ML statut":r.get("ML · Statut")})
    if not table: st.info("Aucun bilan enregistré.")
    else:
        df=pd.DataFrame(table)
        st.dataframe(df,hide_index=True,use_container_width=True)
        both=df.dropna(subset=["Direct (%)","ML (%)"])
        c=st.columns(2)
        for col,field in zip(c,["Direct (%)","ML (%)"]):
            vals=df[field].dropna()
            col.metric(field,f"{vals.mean():.1f} %" if len(vals) else "N/D",help=f"{len(vals)} courses évaluables")
        if len(both):
            st.caption(f"Comparaison à périmètre identique : {len(both)} courses")
            st.plotly_chart(px.bar(both,x="Course",y=["Direct (%)","ML (%)"],barmode="group",range_y=[0,100]),use_container_width=True)
        else: st.info("Pas encore de comparaison ML/direct vérifiable sur un périmètre commun.")
elif page=="Performance":
    render_performance(results,now)
else:
    render_quality(kpis,courses=courses,history=quality_history)
