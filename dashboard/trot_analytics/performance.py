"""Comparable performance of published, verified TOP3 results; read only."""
from collections import Counter, defaultdict
from datetime import date
from .dates import afficher_date
from .logic import number, result_matching

METHODS = ("direct", "ml")


def performance_rows(results, now):
    """One row per unambiguous course; require published matching for both methods."""
    keys = Counter(str(r.get("Clé course (technique)") or "").strip() for r in results)
    rows = []
    for r in results:
        key = str(r.get("Clé course (technique)") or "").strip()
        if not key or keys[key] != 1:
            continue
        try:
            day = date.fromisoformat(str(r.get("Date")))
        except (TypeError, ValueError):
            continue
        # A stored evaluation label must not hide independently verifiable evidence.
        # result_matching checks pre-start Direct timing and score consistency.
        scores = {}
        for method, label in (("direct", "TOP3 direct"), ("ml", "TOP3 ML")):
            published = number(r.get(label + " · Matching (%)"))
            score = result_matching(r, method, now)
            scores[method] = score if published is not None and score is not None and abs(published-score) <= 0.02 else None
        rows.append({"key":key,"date":day,"hippodrome":str(r.get("Hippodrome") or ""),**scores})
    return sorted(rows, key=lambda r:(r["date"],r["key"]))


def summarize(rows):
    paired = [r for r in rows if all(r[m] is not None for m in METHODS)]
    n = len(paired)
    # The only possible stored scores are 0, 33.33, 66.67 and 100.
    # Recover the exact integer counts, avoiding accumulated rounding error.
    hits = {m:sum(round(r[m]*3/100) for r in paired) for m in METHODS}
    return {"courses":n,"evaluated":len(rows),
            "direct_available":sum(r["direct"] is not None for r in rows),
            "ml_available":sum(r["ml"] is not None for r in rows),
            **{m:100*hits[m]/(3*n) if n else None for m in METHODS}}


def evolution(rows):
    days=defaultdict(list)
    for row in rows:
        days[row["date"]].append(row)
    cumulative=[]
    out=[]
    for day, group in sorted(days.items()):
        daily=summarize(group)
        if not daily["courses"]:
            continue
        cumulative.extend(group)
        total=summarize(cumulative)
        out.append({"Date":day,"Courses communes":daily["courses"],
            "TOP3 direct":daily["direct"],"TOP3 ML":daily["ml"],
            "Direct cumulé":total["direct"],"ML cumulé":total["ml"],
            "Courses cumulées":total["courses"]})
    return out


def render_performance(results, now):
    import streamlit as st
    import pandas as pd
    import plotly.express as px

    st.subheader("Efficacité comparative")
    st.caption("Chevaux retrouvés dans le podium, indépendamment de leur ordre. Comparaison sur les mêmes courses, avec deux matchings publiés et vérifiés.")
    rows=performance_rows(results,now)
    if not rows:
        st.info("Aucun résultat vérifiable disponible.")
        return
    start,end=rows[0]["date"],rows[-1]["date"]
    period=st.date_input("Période",value=(start,end),min_value=start,max_value=end,format="DD/MM/YYYY",key="performance_period")
    if not isinstance(period,(tuple,list)) or len(period)!=2:
        st.info("Sélectionner les deux dates de la période.")
        return
    hips=sorted({r["hippodrome"] for r in rows if r["hippodrome"]})
    hip=st.selectbox("Hippodrome",["Tous"]+hips,key="performance_hip")
    filtered=[r for r in rows if period[0]<=r["date"]<=period[1] and (hip=="Tous" or r["hippodrome"]==hip)]
    stats=summarize(filtered)
    cols=st.columns(3)
    cols[0].metric("Courses comparables",f'{stats["courses"]}/{stats["evaluated"]}')
    cols[1].metric("Direct vérifiable",stats["direct_available"])
    cols[2].metric("ML vérifiable",stats["ml_available"])
    if not stats["courses"]:
        st.info("Aucune course avec les deux matchings vérifiés sur cette période. Les valeurs absentes ne sont pas des zéros.")
        return
    labels=["TOP3 direct","TOP3 ML"]
    colors={labels[0]:"#27966c",labels[1]:"#d99b42"}
    values=[stats["direct"],stats["ml"]]
    data=pd.DataFrame({"Méthode":labels,"Matching (%)":values,
                       "Libellé":[f"{v:.2f} %".replace(".",",") for v in values]})
    fig=px.bar(data,x="Matching (%)",y="Méthode",orientation="h",color="Méthode",
               color_discrete_map=colors,text="Libellé",range_x=[0,100])
    fig.update_layout(showlegend=False,height=210,margin=dict(l=0,r=10,t=10,b=10),
                      yaxis=dict(autorange="reversed",title=None),xaxis=dict(ticksuffix="%"))
    fig.update_traces(textposition="auto",cliponaxis=False)
    st.plotly_chart(fig,use_container_width=True)
    delta=values[0]-values[1]
    st.caption(f"Écart direct − ML : {delta:+.2f} points".replace(".",",")+f" · {stats['courses']} courses communes")
    st.subheader("Évolution dans le temps")
    mode=st.radio("Vue",["Cumulée","Par jour"],horizontal=True,key="performance_mode")
    series=pd.DataFrame(evolution(filtered))
    fields=["Direct cumulé","ML cumulé"] if mode=="Cumulée" else labels
    plot=series.rename(columns=dict(zip(fields,labels))) if mode=="Cumulée" else series
    if mode=="Cumulée":
        plot=series[["Date","Courses cumulées",*fields]].rename(columns=dict(zip(fields,labels)))
    plot = plot.assign(Date=plot["Date"].map(afficher_date))
    fig=px.line(plot,x="Date",y=labels,markers=True,range_y=[0,100],
                color_discrete_map=colors,labels={"value":"Matching (%)","variable":"Méthode"},
                hover_data=["Courses cumulées" if mode=="Cumulée" else "Courses communes"])
    fig.update_layout(yaxis=dict(ticksuffix="%"),legend_title_text=None)
    st.plotly_chart(fig,use_container_width=True)
    st.caption("La courbe cumulée pondère chaque course à l’identique. Ces scores décrivent les résultats enregistrés, pas une garantie de performance future.")
    st.dataframe(series.assign(Date=series["Date"].map(afficher_date)),hide_index=True,use_container_width=True)
