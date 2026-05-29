"""Streamlit dashboard — Customer Service Analytics."""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone
from typing import Optional

import pandas as pd
import plotly.express as px
import streamlit as st
import requests

from analytics.database import (
    delete_protocol_rule,
    get_all_analyses,
    get_protocol_rules,
    save_protocol_rule,
)
from analytics.models import FullAnalysis

# ─────────────────── page config ───────────────────

st.set_page_config(
    page_title="Dashboard · Atención al Cliente",
    page_icon="📞",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─────────────────── helpers ───────────────────

@st.cache_data(ttl=60)
def load_analyses() -> list[FullAnalysis]:
    try:
        return get_all_analyses()
    except Exception as exc:
        st.error(f"Error cargando la base de datos de análisis: {exc}")
        return []


@st.cache_data(ttl=10)
def load_protocol_rules() -> dict[str, dict]:
    return get_protocol_rules()


def _utc_to_local_date(dt: datetime) -> date:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone().date()


def to_dataframe(analyses: list[FullAnalysis]) -> pd.DataFrame:
    rows = []
    for a in analyses:
        m = a.math_metrics
        g = a.gemini_analysis
        agent_m = m.speaker_metrics.get(0)
        client_m = m.speaker_metrics.get(1)

        rows.append(
            {
                "id": a.audio_file_id,
                "Nombre": a.original_name,
                "Fecha": _utc_to_local_date(a.uploaded_at),
                "Duración (s)": round(m.total_duration, 1),
                "Interrupciones": m.interruption_count,
                "Interrupciones/min": round(m.interruption_rate, 2),
                "Latencia (s)": m.avg_reaction_time,
                "% Agente": agent_m.monopoly_percentage if agent_m else None,
                "% Cliente": client_m.monopoly_percentage if client_m else None,
                "Categoría": g.visit_category if g else None,
                "Motivo": g.visit_reason if g else None,
                "FCR": g.fcr if g else None,
                "Protocolo %": round(g.protocol.compliance_score * 100, 1) if g else None,
                "_steps": g.protocol.steps if g else {},
                "Sentimiento": g.overall_sentiment if g else None,
                "Justificación FCR": g.fcr_justification if g else None,
            }
        )
    return pd.DataFrame(rows)


def filter_by_period(df: pd.DataFrame, period: str) -> pd.DataFrame:
    today = date.today()
    cutoffs: dict[str, Optional[date]] = {
        "Hoy": today,
        "Últimos 7 días": today - timedelta(days=6),
        "Últimos 30 días": today - timedelta(days=29),
        "Todo el tiempo": None,
    }
    cutoff = cutoffs.get(period)
    if cutoff is None:
        return df
    return df[df["Fecha"] >= cutoff]


def bool_icon(val: Optional[bool]) -> str:
    if val is True:
        return "✅"
    if val is False:
        return "❌"
    return "—"


def _slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9_]", "_", text.strip().lower())


# ─────────────────── sidebar ───────────────────

with st.sidebar:
    st.markdown("## 📞 Atención al Cliente")
    st.markdown("Panel de análisis de calidad")
    st.divider()

    period = st.radio(
        "Período",
        ["Hoy", "Últimos 7 días", "Últimos 30 días", "Todo el tiempo"],
        index=2,
    )
    st.divider()

    uploaded_file = st.file_uploader("Subir archivo de audio (.mp3, .wav)", type=["mp3", "wav"])
    if uploaded_file:
        # Validar usando la extensión del archivo para evitar problemas de tipos MIME
        file_name = uploaded_file.name.lower()
        if not (file_name.endswith('.mp3') or file_name.endswith('.wav')):
            st.error(f"Extensión de archivo no permitida. Solo se aceptan archivos .mp3 y .wav")
        else:
            with st.spinner('Analizando audio automáticamente...'):
                files = {'file': (uploaded_file.name, uploaded_file.getvalue(), uploaded_file.type)}
                response = requests.post('http://127.0.0.1:8000/api/audio/upload/', files=files)
                if response.status_code == 201:
                    st.success("Archivo procesado exitosamente.")
                else:
                    st.error(f"Error al procesar el archivo: {response.status_code} - {response.text}")

    if st.button("🔄 Recargar datos", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

    st.markdown("---")
    st.caption(
        "Ejecuta el pipeline antes de abrir este dashboard:\n"
        "```\npython -m analytics.pipeline\n```"
    )

# ─────────────────── tabs ───────────────────

tab_dash, tab_protocol = st.tabs(["📊 Dashboard", "⚙️ Protocolo"])

# ══════════════════════════════════════════════
# TAB 1 — Dashboard
# ══════════════════════════════════════════════

with tab_dash:
    analyses = load_analyses()
    all_df = to_dataframe(analyses)
    df = filter_by_period(all_df, period)

    st.title("📊 Dashboard · Análisis de Atención al Cliente")

    if df.empty:
        st.info(
            "No hay datos para el período seleccionado. "
            "Sube audios a través de la API Django y ejecuta `python -m analytics.pipeline`."
        )
        st.stop()

    # ── KPIs ──
    k1, k2, k3, k4 = st.columns(4)
    fcr_rate = df["FCR"].dropna().mean() * 100 if df["FCR"].notna().any() else 0.0
    avg_int = df["Interrupciones/min"].mean()
    avg_protocol = df["Protocolo %"].dropna().mean() if df["Protocolo %"].notna().any() else 0.0

    k1.metric("Total atenciones", len(df))
    k2.metric("Resolución en 1ra llamada", f"{fcr_rate:.1f}%")
    k3.metric("Interrupciones / min", f"{avg_int:.2f}")
    k4.metric("Cumplimiento de protocolo", f"{avg_protocol:.1f}%")

    st.divider()

    # ── Monopolio + Latencia ──
    col_mono, col_lat = st.columns(2)

    with col_mono:
        st.subheader("Monopolio de Conversación")
        avg_agent = df["% Agente"].dropna().mean()
        avg_client = df["% Cliente"].dropna().mean()
        if pd.notna(avg_agent) and pd.notna(avg_client):
            pie_df = pd.DataFrame(
                {
                    "Hablante": ["Agente (Speaker 0)", "Cliente (Speaker 1)"],
                    "% Tiempo": [avg_agent, avg_client],
                }
            )
            fig_pie = px.pie(
                pie_df, names="Hablante", values="% Tiempo",
                color_discrete_sequence=["#636EFA", "#EF553B"], hole=0.45,
            )
            fig_pie.update_traces(textinfo="percent+label")
            fig_pie.update_layout(margin=dict(t=10, b=10, l=10, r=10), showlegend=False)
            st.plotly_chart(fig_pie, use_container_width=True)
        else:
            st.info("Sin datos de monopolio.")

    with col_lat:
        st.subheader("Latencia Promedio por Fecha")
        lat_df = (
            df.dropna(subset=["Latencia (s)"])
            .groupby("Fecha")["Latencia (s)"]
            .mean().reset_index().sort_values("Fecha")
        )
        if not lat_df.empty:
            fig_line = px.line(
                lat_df, x="Fecha", y="Latencia (s)", markers=True,
                color_discrete_sequence=["#00CC96"],
            )
            fig_line.update_layout(margin=dict(t=10, b=10, l=10, r=10))
            st.plotly_chart(fig_line, use_container_width=True)
        else:
            st.info("Sin datos de latencia.")

    # ── Categorías + Protocolo dinámico ──
    col_cat, col_proto = st.columns(2)

    with col_cat:
        st.subheader("Distribución por Categoría")
        cat_df = (
            df.dropna(subset=["Categoría"])["Categoría"]
            .value_counts().reset_index()
        )
        cat_df.columns = ["Categoría", "Cantidad"]
        if not cat_df.empty:
            fig_cat = px.bar(
                cat_df, x="Categoría", y="Cantidad",
                color="Categoría", text="Cantidad",
                color_discrete_sequence=px.colors.qualitative.Plotly,
            )
            fig_cat.update_traces(textposition="outside")
            fig_cat.update_layout(showlegend=False, margin=dict(t=10, b=10, l=10, r=10))
            st.plotly_chart(fig_cat, use_container_width=True)
        else:
            st.info("Sin datos de categoría.")

    with col_proto:
        st.subheader("Cumplimiento por Paso de Protocolo")
        current_rules = load_protocol_rules()

        # Aggregate compliance per step across all analyses in view
        step_totals: dict[str, list[bool]] = {}
        for _, row in df.iterrows():
            steps: dict = row.get("_steps") or {}
            for key, val in steps.items():
                step_totals.setdefault(key, []).append(bool(val))

        if step_totals:
            proto_rows = []
            for key, values in step_totals.items():
                label = current_rules.get(key, {}).get("label", key)
                proto_rows.append(
                    {"Paso": label, "% Cumplimiento": sum(values) / len(values) * 100}
                )
            proto_df = pd.DataFrame(proto_rows).sort_values("% Cumplimiento")
            fig_proto = px.bar(
                proto_df, x="% Cumplimiento", y="Paso", orientation="h",
                color="% Cumplimiento", color_continuous_scale="RdYlGn",
                range_color=[0, 100],
                text=proto_df["% Cumplimiento"].apply(lambda v: f"{v:.0f}%"),
            )
            fig_proto.update_traces(textposition="outside")
            fig_proto.update_layout(
                coloraxis_showscale=False,
                margin=dict(t=10, b=10, l=10, r=120),
                xaxis_range=[0, 115],
            )
            st.plotly_chart(fig_proto, use_container_width=True)
        else:
            st.info("Sin datos de protocolo.")

    # ── FCR trend ──
    st.subheader("Tasa de Resolución FCR por Fecha")
    fcr_trend = (
        df.dropna(subset=["FCR"])
        .groupby("Fecha")["FCR"]
        .apply(lambda x: x.mean() * 100)
        .reset_index().rename(columns={"FCR": "FCR (%)"})
        .sort_values("Fecha")
    )
    if not fcr_trend.empty:
        fig_fcr = px.area(
            fcr_trend, x="Fecha", y="FCR (%)", markers=True,
            color_discrete_sequence=["#AB63FA"], range_y=[0, 105],
        )
        fig_fcr.add_hline(y=80, line_dash="dot", line_color="green", annotation_text="Meta 80%")
        fig_fcr.update_layout(margin=dict(t=10, b=10, l=10, r=10))
        st.plotly_chart(fig_fcr, use_container_width=True)
    else:
        st.info("Sin datos de FCR.")

    # ── Tabla ──
    st.divider()
    st.subheader("Tabla de Atenciones")
    table_df = df[
        ["Nombre", "Fecha", "Duración (s)", "Categoría", "FCR", "Protocolo %",
         "Interrupciones/min", "Latencia (s)", "Sentimiento", "Motivo"]
    ].copy()
    table_df["FCR"] = table_df["FCR"].map(bool_icon)
    st.dataframe(
        table_df, use_container_width=True, hide_index=True,
        column_config={
            "Protocolo %": st.column_config.ProgressColumn(
                "Protocolo %", min_value=0, max_value=100, format="%.1f%%"
            ),
            "Duración (s)": st.column_config.NumberColumn("Duración (s)", format="%.0f s"),
            "Latencia (s)": st.column_config.NumberColumn("Latencia (s)", format="%.2f s"),
            "Interrupciones/min": st.column_config.NumberColumn("Interrupciones/min", format="%.2f"),
        },
    )

    # ── Detalle ──
    st.divider()
    st.subheader("Detalle de Atención")
    selected_name = st.selectbox("Selecciona una atención", options=df["Nombre"].tolist())
    sel = df[df["Nombre"] == selected_name]
    if not sel.empty:
        row = sel.iloc[0]
        d1, d2, d3 = st.columns(3)
        d1.metric("Duración total", f"{row['Duración (s)']} s")
        d2.metric("Interrupciones/min", f"{row['Interrupciones/min']}")
        d3.metric("Latencia promedio", f"{row['Latencia (s)']} s")

        if pd.notna(row.get("% Agente")):
            mono_fig = px.pie(
                pd.DataFrame({
                    "Hablante": ["Agente", "Cliente"],
                    "% Tiempo": [row["% Agente"], row["% Cliente"]],
                }),
                names="Hablante", values="% Tiempo", hole=0.5,
                color_discrete_sequence=["#636EFA", "#EF553B"],
                title="Distribución del tiempo en esta llamada",
            )
            mono_fig.update_layout(margin=dict(t=40, b=10, l=10, r=10))
            st.plotly_chart(mono_fig, use_container_width=True)

        steps: dict = row.get("_steps") or {}
        if steps:
            st.markdown(f"**Categoría:** {row['Categoría']}  \n**Motivo:** {row['Motivo']}")
            st.markdown(
                f"**FCR:** {bool_icon(row['FCR'] == '✅')}  \n"
                f"**Justificación:** {row.get('Justificación FCR', '—')}"
            )
            st.markdown(f"**Sentimiento:** {row.get('Sentimiento', '—')}")
            st.markdown("**Checklist de protocolo:**")
            current_rules = load_protocol_rules()
            check_df = pd.DataFrame([
                {
                    "Paso": current_rules.get(k, {}).get("label", k),
                    "Estado": bool_icon(v),
                }
                for k, v in steps.items()
            ])
            st.dataframe(check_df, hide_index=True, use_container_width=False)


# ══════════════════════════════════════════════
# TAB 2 — Configuración de Protocolo
# ══════════════════════════════════════════════

with tab_protocol:
    st.title("⚙️ Configuración de Protocolo")
    st.markdown(
        "Estos pasos se usan en el **siguiente análisis** que ejecutes con el pipeline. "
        "Los análisis ya guardados no se modifican retroactivamente."
    )

    rules = get_protocol_rules()

    if not rules:
        st.info("No hay pasos definidos. Agrega uno abajo.")
    else:
        st.subheader("Pasos actuales")
        for key, info in rules.items():
            with st.container(border=True):
                c1, c2 = st.columns([10, 1])
                with c1:
                    st.markdown(f"**{info['label']}**")
                    st.caption(info["description"])
                with c2:
                    if st.button("🗑️", key=f"del_{key}", help="Eliminar este paso"):
                        delete_protocol_rule(key)
                        st.cache_data.clear()
                        st.rerun()

    st.divider()
    st.subheader("Agregar / editar paso")

    with st.form("add_protocol_rule", clear_on_submit=True):
        col_a, col_b = st.columns(2)
        new_label = col_a.text_input(
            "Nombre corto",
            placeholder="ej: Verificó identidad",
            help="Aparece en el dashboard y la tabla",
        )
        new_desc = col_b.text_input(
            "Criterio para Gemini",
            placeholder="ej: El agente verificó la identidad del cliente solicitando DNI o número de cuenta",
            help="Descripción completa que Gemini usará para evaluar el paso",
        )
        submitted = st.form_submit_button("➕ Agregar paso", use_container_width=True)

        if submitted:
            if not new_label.strip() or not new_desc.strip():
                st.error("Completa ambos campos.")
            else:
                key = _slugify(new_label)
                save_protocol_rule(key, new_label.strip(), new_desc.strip())
                st.cache_data.clear()
                st.success(f"Paso **{new_label}** guardado.")
                st.rerun()

    st.divider()
    st.info(
        "💡 **Tip:** después de editar el protocolo, volvé a correr el pipeline "
        "para que los nuevos análisis usen los pasos actualizados:\n"
        "```\npython -m analytics.pipeline\n```"
    )
