"""Compact, read-only presentation of the published quality indicators."""
from collections import OrderedDict
from datetime import timezone
from .dates import afficher_date, afficher_instant, afficher_valeur_kpi, indicateur_horodate
from .logic import number,timestamp
from .correspondance_geny import KPI_PREFIX

TOTAL_FIELD = "Total de référence (automatique)"
COLUMNS = ["Indicateur", "Description", "Nombre / valeur", "Total"]


def display_value(value, *, rate=False):
    if value is None or value == "":
        return "—"
    numeric = number(value)
    if numeric is None:
        return afficher_instant(value, timezone.utc) or str(value)
    if rate:
        return f"{numeric * 100:.1f}".replace(".", ",") + " %"
    if numeric.is_integer():
        return f"{int(numeric):,}".replace(",", "\u202f")
    return f"{numeric:,.2f}".replace(",", "\u202f").replace(".", ",")


def is_rate(label):
    return label.startswith(("Taux", "Maturité ML · Taux", "Maturité ML · Couverture ·", "Cotes PMU · Taux"))


def quality_sections(kpis, query=""):
    """Keep the source denominator; no ratio or total is inferred by the UI."""
    sections = OrderedDict()
    query = query.strip().casefold()
    for row in kpis:
        label = str(row.get("Indicateur") or "").strip()
        if not label:
            continue
        definition = str(row.get("Définition / réserve") or "").strip()
        dimension = str(row.get("Dimension") or "Autres").strip() or "Autres"
        # These new metrics can still be published under the generic ML dimension.
        if label.startswith("Maturité ML · "):
            dimension = "Maturité ML"
        elif label.startswith("Autostart prospectif · "):
            dimension = "Autostart prospectif"
        elif label.startswith(("Échéances · H1 ", "Échéances · H2 ")):
            dimension = "Échéances · Historique H-2/H-1"
        elif label.startswith(("Échéances · ", "H+30 · ")):
            dimension = "Échéances"
        elif label.startswith("Collecte · "):
            dimension = "Collecte"
        elif label.startswith(("J · ", "J+1 · ", "Registre · ")):
            dimension = "Lecture Sheets J/J+1"
        elif label.startswith(KPI_PREFIX):
            dimension = "Correspondance PMU–Geny"
        elif label.startswith("Rattrapage · "):
            dimension = "Rattrapage"
        if query and query not in f"{dimension} {label} {definition}".casefold():
            continue
        sections.setdefault(dimension, []).append({
            "Indicateur": label.removesuffix(" UTC") + " (Paris)" if indicateur_horodate(label) else label,
            "Description": definition or "—",
            "Nombre / valeur": display_value(afficher_valeur_kpi(label, row.get("Valeur (automatique)")), rate=is_rate(label)),
            "Total": display_value(row.get(TOTAL_FIELD)),
        })
    return sections


def render_quality(kpis, courses=None, history=None):
    import pandas as pd
    import streamlit as st
    from datetime import datetime
    from zoneinfo import ZoneInfo
    from .quality_dates import cohort_metrics, daily_series, history_series, latest_history, date_rows

    modes=["Courses de la période", "Relevés historiques", "Registre actuel"] if courses is not None else ["Registre actuel"]
    controls=st.columns(2)
    mode=controls[0].selectbox("Lecture des indicateurs",modes,key="quality_mode")
    series=[]
    if mode!="Registre actuel":
        today=datetime.now(ZoneInfo('Europe/Paris')).date()
        interval=controls[1].date_input("Période — une date ou un intervalle",value=(today,today),format="DD/MM/YYYY",key="quality_period")
        if len(interval)!=2:
            st.info("Choisissez la date de fin ; pour une seule journée, choisissez deux fois la même date.")
            return
        start,end=interval
        if mode=="Courses de la période":
            st.caption("État actuel des données des courses de la période. Cette comparaison ne reconstitue pas leur état passé.")
            if not date_rows(courses or [],'Date',start,end):
                st.info("Aucune course enregistrée pour cette période.")
                return
            kpis=cohort_metrics(courses,start,end)
            series=daily_series(courses,start,end)
        else:
            st.caption("Dernier relevé conservé pour chaque jour d’observation, heure de Paris. La journée en cours reste actualisable.")
            try:series=history_series(history or [],start,end)
            except ValueError:
                st.error("Historique incohérent : vérifiez les doublons et les dates des relevés.")
                return
            kpis,latest=latest_history(series)
            if not kpis:
                st.info("Aucun relevé conservé pour cette période. Le passé n’est pas reconstitué à partir des valeurs actuelles.")
                return
            st.caption("Tableaux : dernier relevé de la période, le "+str(afficher_date(latest))+". Évolution : ensemble des relevés sélectionnés.")
            observed=max(timestamp(r['Relevé UTC']) for r in kpis)
            st.caption("Observation : "+afficher_instant(observed)+" (Paris).")
    else:
        st.caption("Indicateurs globaux actuels du registre, sans filtre de date.")
    if not any(row.get("Indicateur") for row in kpis):
        st.info("KPI indisponibles.")
        return
    sections = quality_sections(kpis)
    filters = st.columns(2)
    section = filters[0].selectbox("Section", ["Toutes les sections", *sections], key="quality_section")
    query = filters[1].text_input("Rechercher un indicateur", placeholder="Ferrure, historique, ML…", key="quality_search")
    visible = quality_sections(kpis, query)
    if section != "Toutes les sections":
        visible = {section: visible[section]} if section in visible else {}
    count = sum(len(rows) for rows in visible.values())
    st.caption(f"{count} indicateurs · {len(visible)} sections · Total : valeur de référence publiée ; — : non renseigné.")
    if not visible:
        st.info("Aucun indicateur ne correspond à ces filtres.")
        return
    if series:
        numeric = [r for r in series if not indicateur_horodate(r.get('Indicateur'))
                   and number(r.get('Valeur (automatique)')) is not None]
        labels=sorted({r['Indicateur'] for r in numeric})
        with st.expander("Évolution d’un indicateur",expanded=False):
            st.caption("Les totaux de référence sont affichés pour comparer des périmètres qui peuvent évoluer.")
            if labels:
                choice=st.selectbox("Indicateur à suivre",labels,key="quality_trend")
                points=sorted([r for r in numeric if r['Indicateur']==choice],key=lambda r:r['Date'])
                rate=is_rate(choice)
                frame=pd.DataFrame([{'Date':afficher_date(r['Date']),'Valeur (%)' if rate else 'Valeur':number(r['Valeur (automatique)'])*(100 if rate else 1)} for r in points])
                if len(frame)>1:
                    import plotly.express as px
                    frame['Date'] = pd.to_datetime(frame['Date'], format='%d/%m/%Y')
                    fig = px.line(frame, x='Date', y=frame.columns[1], height=220)
                    fig.update_xaxes(tickformat='%d/%m/%Y', hoverformat='%d/%m/%Y')
                    st.plotly_chart(fig, width="stretch")
                else:st.info("Un seul jour disponible : il faut au moins deux dates pour observer une évolution.")
                st.dataframe(pd.DataFrame([{'Date':afficher_date(r['Date']),'Nombre / valeur':display_value(r.get('Valeur (automatique)'),rate=rate),
                                           'Total':display_value(r.get(TOTAL_FIELD))} for r in points]),hide_index=True,width="stretch",height=min(250,35*(len(points)+1)+3))
            else:st.info("Aucune valeur numérique disponible pour tracer une évolution.")
    for index, (dimension, rows) in enumerate(visible.items()):
        with st.expander(f"{dimension} · {len(rows)} indicateurs", expanded=index == 0):
            st.dataframe(
                pd.DataFrame(rows, columns=COLUMNS),
                column_config={
                    "Indicateur": st.column_config.TextColumn(width="medium"),
                    "Description": st.column_config.TextColumn(width="large"),
                    "Nombre / valeur": st.column_config.TextColumn(width="small"),
                    "Total": st.column_config.TextColumn(width="small", help="Total repris du registre, sans recalcul."),
                },
                hide_index=True, width="stretch",
                height=min(400, 35 * (len(rows) + 1) + 3),
            )
