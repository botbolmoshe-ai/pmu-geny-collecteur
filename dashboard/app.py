import streamlit as st
import pandas as pd
import plotly.express as px
import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from trot_analytics.dates import afficher_instant
from trot_analytics.logic import couverture_reunions, records, selected, number, timestamp, result_matching
from trot_analytics.quality import render_quality
from trot_analytics.performance import render_performance
from trot_analytics.observations import tableau_observations
from trot_analytics.usages import IPR
from trot_analytics.profils import (
    AUCUN_PROFIL, COLONNE_INDICES, COLONNE_PROFIL, NON_EVALUABLE, PALETTE,
    SEPARATEUR_PROFILS, libelles_profils,
)

st.set_page_config(page_title="TROT Analytics",page_icon="📊",layout="wide")
PARIS=ZoneInfo("Europe/Paris")
TABS=("Courses & Prévisions","Résultats & Analyse","Data Quality & KPI")
HISTORY_TAB="Historique qualité"
SCOPES=["https://www.googleapis.com/auth/spreadsheets.readonly"]

@st.cache_data(ttl=120,show_spinner=False)
def read_registry():
    creds=Credentials.from_service_account_info(dict(st.secrets["google_service_account"]),scopes=SCOPES)
    api=build("sheets","v4",credentials=creds,cache_discovery=False)
    ranges=[f"'{TABS[0]}'", *(f"'{tab}'!A1:AZ" for tab in TABS[1:])]
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
st.caption("Version interface : 2026.11.23 · Observations IPR")
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
st.caption("Registre lu à "+afficher_instant(loaded)+" (Paris) · fraîcheur des fiches distincte")
page=st.radio("Navigation",["Accueil","Courses","Résultats","Performance","Qualité"],horizontal=True,label_visibility="collapsed")
if page in ("Accueil","Courses","Résultats"):
    dates=sorted({str(r.get("Date")) for r in courses if r.get("Date")})
    today=now.astimezone(PARIS).date().isoformat()
    day=st.date_input("Date",value=now.astimezone(PARIS).date(),format="DD/MM/YYYY").isoformat()
    groups={}
    for row in courses:
        if str(row.get("Date"))==day and row.get("Clé course (technique)"):
            groups.setdefault(row["Clé course (technique)"],[]).append(row)
    groups=dict(sorted(groups.items(),key=lambda kv: str(kv[1][0].get("Départ (Paris)",""))))
    hips=sorted({str(rows[0].get("Hippodrome","")) for rows in groups.values()} | ({str(r.get("Hippodrome","")) for r in results if str(r.get("Date"))==day} if page=="Résultats" else set()))
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
    coverage = couverture_reunions(groups, now)
    if coverage:
        st.subheader("Couverture des prochaines réunions")
        st.dataframe(pd.DataFrame(coverage), hide_index=True, use_container_width=True)
    st.subheader("Prochains départs")
    upcoming=[r[0] for r in groups.values() if timestamp(r[0].get("Départ (Paris)")) and timestamp(r[0]["Départ (Paris)"])>now]
    if upcoming:
        table = pd.DataFrame(upcoming).reindex(columns=["Course R/C","Hippodrome","Départ (Paris)","Discipline"])
        table["Départ (Paris)"] = table["Départ (Paris)"].map(afficher_instant)
        st.dataframe(table,hide_index=True,use_container_width=True)
    else: st.caption("Aucun départ futur enregistré pour cette date.")
elif page=="Courses":
    def badges(libelles):
        return " ".join(
            f'<span style="background-color:{fond};color:{texte};padding:.15em .45em;'
            f'border-radius:.25em;font-weight:bold">{icone} {libelle}</span>'
            for libelle in libelles if libelle in PALETTE
            for fond, texte, icone in (PALETTE[libelle],)
        )

    def profils_ligne(row):
        if row.get("Non-partant (NP)") == "NON_PARTANT":
            return ()
        return libelles_profils(row.get(COLONNE_PROFIL)) or (NON_EVALUABLE,)

    profil_filtre = st.multiselect("Filtrer les partants par profil",
                                  [*PALETTE, NON_EVALUABLE, AUCUN_PROFIL], key="profils_filtre")
    if groups:
        st.html(badges(PALETTE))
        st.caption("Le violet/or est prioritaire sur la ligne si les deux profils sont présents. "
                   "Non évaluable indique que les preuves nécessaires ne sont pas disponibles.")
    else:
        st.info("Aucune course pour ce filtre.")
    for key,rows in groups.items():
        first=rows[0]; depart=timestamp(first.get("Départ (Paris)"))
        label=first.get("Course R/C","")+" · "+str(first.get("Hippodrome",""))+" · "+(afficher_instant(depart) if depart else "heure inconnue")
        if first.get("Course · Nom PMU"):
            label += " · " + str(first["Course · Nom PMU"])
        with st.expander(label,expanded=len(groups)==1):
            st.caption("Course passée — prévisions archivées" if depart and depart<=now else "Prévisions stockées · non recalculées")
            discipline = {"TROT_ATTELE": "Trot attelé", "TROT_MONTE": "Trot monté"}.get(
                first.get("Discipline"), first.get("Discipline"))
            conditions = str(first.get("Conditions de course") or "")
            gains = re.search(
                r"\b(?:n['’]ayant pas gagné|ayant gagné|à réclamer pour)\s+[^.;]+"
                r"(?:[., \u202f]\d{3}\b[^.;]*)*", conditions, re.IGNORECASE)
            count = sum(row.get("Non-partant (NP)") == "PARTANT" for row in rows)
            count_label = f"{count} partant{'s' if count > 1 else ''}" if all(
                row.get("Non-partant (NP)") in ("PARTANT", "NON_PARTANT") for row in rows
            ) else f"{len(rows)} inscrits"

            def fmt(value, unit):
                value = number(value)
                return f"{value:,.0f} {unit}".replace(",", "\u202f") if value is not None else ""

            for items in (
                (discipline, first.get("Course · Catégorie PMU"),
                 fmt(first.get("Distance (m)"), "m"), fmt(first.get("Course · Allocation (€)"), "€")),
                (first.get("Course · Âges admis"), gains.group() if gains else None,
                 first.get("Course · Parcours"), first.get("Course · Mode de départ")),
                (count_label, first.get("Météo · Synthèse")),
            ):
                context = " · ".join(str(value) for value in items if value)
                if context:
                    st.caption(context)
            if conditions:
                with st.popover("Conditions détaillées"):
                    st.write(conditions)
            for method,title in [("direct","TOP3 direct"),("ml","TOP3 ML")]:
                chosen=selected(rows,method)
                if chosen:
                    st.markdown("**"+title+" : "+" — ".join(str(h["N°"]) for h in chosen)+"**")
                    st.caption(" / ".join(str(h.get("Cheval","")) for h in chosen))
                else: st.caption(title+" : sélection indisponible ou non vérifiée")
                winner_label = "Gagnant potentiel " + title.removeprefix("TOP3 ")
                if chosen and chosen[0].get(winner_label + " · Sélection") == "OUI":
                    winner = chosen[0]
                    st.markdown(f"**{winner_label} : {winner['N°']} — {winner.get('Cheval') or '—'}**")
                else:
                    st.caption(winner_label + " : indisponible")
            st.caption("Calcul direct : "+(afficher_instant(first.get("TOP3 direct · Calcul UTC")) + " (Paris)" if timestamp(first.get("TOP3 direct · Calcul UTC")) else "non renseigné"))
            st.caption("ML : "+str(first.get("ML · État du modèle") or "non renseigné"))
            st.caption("NP : "+", ".join(str(h["N°"]) for h in rows if h.get("Non-partant (NP)")=="NON_PARTANT") if any(h.get("Non-partant (NP)")=="NON_PARTANT" for h in rows) else "Aucun NP enregistré (voir fraîcheur des fiches)")
            odds_top3 = selected(rows, "cotes")
            if odds_top3:
                state = " (partiel)" if odds_top3[0].get("Cotes · État") == "PARTIEL" else ""
                st.markdown(f"**TOP3 Cotes{state}** · " + " — ".join(str(h["N°"]) for h in odds_top3))
            else:
                st.caption("TOP3 Cotes indisponible")
            odds = []
            odds_times = []
            for row in rows:
                stamp = timestamp(row.get("Cotes · Relevé UTC"))
                value = number(row.get("Cotes · Valeur"))
                if (value is not None and value > 0 and stamp and depart and stamp < depart
                        and stamp <= now and row.get("Non-partant (NP)") != "NON_PARTANT"):
                    odds.append(value)
                    odds_times.append(stamp)
                else:
                    odds.append(None)
            latest_odds = max(odds_times, default=None)
            if latest_odds:
                st.caption("Dernier relevé PMU à " + afficher_instant(latest_odds)
                           + " (Paris)")
            visibles = [not profil_filtre or bool(set(profil_filtre).intersection(profils_ligne(row)))
                        for row in rows]
            if not any(visibles):
                st.caption("Aucun partant pour les profils sélectionnés.")
                continue
            columns = ["N°", "Cheval", "Cote PMU", "Âge (ans)", COLONNE_PROFIL, COLONNE_INDICES, "Ferrure", "Musique PMU",
                       "Non-partant (NP)", "Historique · Nb performances récupérées",
                       "Données actuelles · Mise à jour UTC"]
            partants = pd.DataFrame(rows)
            partants["Cote PMU"] = odds
            if "Ferrure" not in partants and "Ferrure · Course du jour" in partants:
                partants = partants.rename(columns={"Ferrure · Course du jour": "Ferrure"})
            for field in ("Autostart · Position assignée", "Autostart · Ligne", "Départ · Recul (m)"):
                if field in partants:
                    partants[field] = [
                        number(row.get(field)) if row.get("Non-partant (NP)") == "PARTANT" else None
                        for row in rows
                    ]
                    if partants[field].notna().any():
                        columns.append(field)
            partants = partants.reindex(columns=columns)
            partants["Données actuelles · Mise à jour UTC"] = partants["Données actuelles · Mise à jour UTC"].map(
                afficher_instant)
            partants = partants.rename(columns={"Données actuelles · Mise à jour UTC": "Données actuelles · Mise à jour (Paris)"})
            partants[COLONNE_PROFIL] = [SEPARATEUR_PROFILS.join(profils_ligne(row)) for row in rows]
            partants = partants.loc[visibles]
            styles = partants[COLONNE_PROFIL].map(lambda valeur: libelles_profils(valeur)[:1]).map(
                lambda profils: PALETTE.get(profils[0]) if profils else None)
            if styles.notna().any():
                styles = styles.map(lambda couleur: (
                    f"background-color: {couleur[0]}; color: {couleur[1]}; font-weight: bold"
                    if couleur else ""))
                partants = partants.style.apply(lambda _: styles, subset=["Cheval", COLONNE_PROFIL])
            st.dataframe(partants, hide_index=True, use_container_width=True,
                         column_config={"Cote PMU": st.column_config.NumberColumn(format="localized", width="small")})
            fiches = [row for row, visible in zip(rows, visibles) if visible]
            if observations := tableau_observations(fiches, IPR):
                st.markdown("#### Indice de performance relative")
                st.html(observations)
            fiche = st.selectbox("Fiche cheval", range(len(fiches)), index=None,
                                 format_func=lambda i: f"{fiches[i]['N°']} · {fiches[i]['Cheval']}",
                                 key=f"fiche_{key}")
            if fiche is not None:
                row = fiches[fiche]
                libelles = profils_ligne(row)
                if rendu := badges(libelles):
                    st.html(rendu)
                else:
                    st.text(SEPARATEUR_PROFILS.join(libelles) or "Non-partant")
                st.text(str(row.get(COLONNE_INDICES) or "Aucun indice archivé pour cette fiche."))
elif page=="Résultats":
    st.caption("Matching en % · uniquement sur preuves disponibles. Absence ≠ 0 %. ML non évaluable sans preuve enregistrée.")
    table=[]
    for r in day_results:
        direct_score = result_matching(r, "direct", now)
        recorded_state = r.get("Évaluation · État")
        display_state = recorded_state
        if direct_score is not None and recorded_state != "EVALUE":
            display_state = "EVALUE_DIRECT"
        row = {"Course":r.get("Course R/C"),
            "Direct":r.get("TOP3 direct · Chevaux"),"Direct · Noms":r.get("TOP3 direct · Noms"),
            "ML":r.get("TOP3 ML · Chevaux"),"ML · Noms":r.get("TOP3 ML · Noms"),
            "Podium enregistré":r.get("Arrivée · N° officiels"),"Podium · Noms":r.get("Arrivée · Noms officiels"),
            "Direct (%)":direct_score,
            "ML (%)":result_matching(r,"ml",now),
            "État":display_state,
            "État enregistré":recorded_state,"ML statut":r.get("ML · Statut"),
            "Départ prévu (Paris)":afficher_instant(r.get("Départ (Paris)")),
            "Arrivée lue dans le flux PMU (Paris)":afficher_instant(r.get("Arrivée · Vérifiée UTC")),
            "Conclusion Direct / ML":r.get("Évaluation · Conclusion")}
        for mode in ("direct", "ML"):
            for field in ("N°", "Nom", "Rang officiel", "Verdict"):
                key = f"Gagnant potentiel {mode} · {field}"
                row[key] = r.get(key) or None
            key = f"Gagnant potentiel {mode} · Nom"
            top3 = "TOP3 direct" if mode == "direct" else "TOP3 ML"
            names = str(r.get(top3 + " · Noms") or "").split(" · ")
            numbers = str(r.get(top3 + " · Chevaux") or "").split(",")
            winner = number(r.get(f"Gagnant potentiel {mode} · N°"))
            row[key] = names[0] if winner and winner == number(numbers[0]) and len(names) == 3 else None
        row["Jalon comparé"] = r.get("Jalon comparé") or None
        for phase in ("H-3", "H-2"):
            row[f"{phase} · État"] = r.get(f"{phase} · État") or None
            for field in ("Échéance", "Publication"):
                row[f"{phase} · {field} (Paris)"] = afficher_instant(r.get(f"{phase} · {field} UTC"))
            for method in ("Direct", "ML"):
                label = f"Score {phase} · {method}"
                row[label] = number(r.get(label))
        table.append(row)
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
