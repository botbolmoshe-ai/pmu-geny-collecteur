"""Compact, read-only presentation of the published quality indicators."""
from collections import OrderedDict
from logic import number

TOTAL_FIELD = "Total de référence (automatique)"
COLUMNS = ["Indicateur", "Description", "Nombre / valeur", "Total"]


def display_value(value, *, rate=False):
    if value is None or value == "":
        return "—"
    numeric = number(value)
    if numeric is None:
        return str(value)
    if rate:
        return f"{numeric * 100:.1f}".replace(".", ",") + " %"
    if numeric.is_integer():
        return f"{int(numeric):,}".replace(",", "\u202f")
    return f"{numeric:,.2f}".replace(",", "\u202f").replace(".", ",")


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
        if label.startswith("Échéances · "):
            dimension = "Échéances"
        elif label.startswith("Collecte · "):
            dimension = "Collecte"
        if query and query not in f"{dimension} {label} {definition}".casefold():
            continue
        sections.setdefault(dimension, []).append({
            "Indicateur": label,
            "Description": definition or "—",
            "Nombre / valeur": display_value(row.get("Valeur (automatique)"), rate=label.startswith("Taux")),
            "Total": display_value(row.get(TOTAL_FIELD)),
        })
    return sections


def render_quality(kpis):
    import pandas as pd
    import streamlit as st

    st.caption("Indicateurs globaux du registre · le filtre de date ne s’applique pas ici.")
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
