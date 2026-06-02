import asyncio
import re
from datetime import date, datetime, timedelta, timezone

import pandas as pd
import plotly.express as px
from django.shortcuts import render, redirect, get_object_or_404

from .forms import AudioFileUploadForm
from analytics.database import (
    delete_protocol_rule,
    get_all_analyses,
    get_analysis,
    get_protocol_rules,
    save_protocol_rule,
)
from analytics.pipeline import run_pipeline
from audio_upload.models import AudioFile
from audio_upload.services import transcribe_audio


def _slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9_]", "_", text.strip().lower())


def _utc_to_local_date(dt: datetime) -> date:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone().date()


def _resolve_speaker_ids(g, sm_keys: set) -> tuple[set, set]:
    """
    Return (agent_ids, client_ids) resolving any missing role from the remaining
    speakers. Falls back to 0=agent / 1=client only when both sets are absent.
    Returns (set(), set()) if the roles can't be distinguished (e.g. single speaker).
    """
    agent_ids = set(g.agent_speaker_ids) if g.agent_speaker_ids else None
    client_ids = set(g.client_speaker_ids) if g.client_speaker_ids else None

    if agent_ids is None and client_ids is None:
        sorted_s = sorted(sm_keys)
        agent_ids = {sorted_s[0]} if len(sorted_s) >= 1 else set()
        client_ids = {sorted_s[1]} if len(sorted_s) >= 2 else set()
    elif agent_ids is None:
        agent_ids = sm_keys - client_ids
    elif client_ids is None:
        client_ids = sm_keys - agent_ids

    # Remove speakers that appear in both roles (ambiguous)
    overlap = agent_ids & client_ids
    if overlap:
        agent_ids -= overlap
        client_ids -= overlap

    if not agent_ids or not client_ids:
        return set(), set()
    return agent_ids, client_ids


# ── Emerald palette for charts ───────────────────────────────────────────
_EM = {
    'agent':   '#10b981',   # emerald-500  (agente en pie)
    'client':  '#0ea5e9',   # sky-500      (cliente en pie — contraste claro)
    'primary': '#10b981',   # líneas / áreas principales
    'fill':    'rgba(16,185,129,.15)',  # relleno área
    'meta':    '#059669',   # líneas de referencia / metas
    'categories': [         # paleta para barras multi-categoría
        '#10b981', '#0ea5e9', '#f59e0b', '#f43f5e', '#8b5cf6', '#0d9488',
    ],
    'scale_compliance': [   # escala continua: bajo→alto
        [0.0, '#ef4444'],   # rojo
        [0.5, '#f59e0b'],   # ámbar
        [1.0, '#10b981'],   # esmeralda
    ],
}

_FONT = dict(family='Inter, system-ui, sans-serif', size=12, color='#6b7280')
_TRANSPARENT = 'rgba(0,0,0,0)'

def _base_layout(**extra) -> dict:
    """Shared Plotly layout: transparent bg, Inter font, subtle grid."""
    base = dict(
        paper_bgcolor=_TRANSPARENT,
        plot_bgcolor=_TRANSPARENT,
        font=_FONT,
        margin=dict(t=10, b=10, l=10, r=10),
        xaxis=dict(gridcolor='#f3f4f6', zerolinecolor='#e5e7eb'),
        yaxis=dict(gridcolor='#f3f4f6', zerolinecolor='#e5e7eb'),
    )
    base.update(extra)
    return base


def _chart_html(fig) -> str:
    return fig.to_html(full_html=False, include_plotlyjs=False)


def upload_audio(request):
    if request.method == 'POST':
        form = AudioFileUploadForm(request.POST, request.FILES)
        if form.is_valid():
            audio_file = form.save(commit=False)
            uploaded_file = request.FILES['file']
            audio_file.original_name = uploaded_file.name
            audio_file.content_type = uploaded_file.content_type
            audio_file.size_bytes = uploaded_file.size
            audio_file.save()

            try:
                result = transcribe_audio(audio_file.file.path)
                audio_file.transcription = result['transcript']
                audio_file.diarization = result['diarization']
                audio_file.sentiment = result['sentiment']
                audio_file.detected_language = result.get('detected_language') or ''
                audio_file.transcription_status = 'completed'
            except Exception:
                audio_file.transcription_status = 'failed'

            audio_file.save(update_fields=[
                'transcription', 'transcription_status',
                'diarization', 'sentiment', 'detected_language',
            ])

            asyncio.run(run_pipeline())
            return redirect('dashboard')
    else:
        form = AudioFileUploadForm()
    return render(request, 'upload.html', {'form': form})


def dashboard(request):
    if request.method == 'POST':
        if 'add_rule' in request.POST:
            label = request.POST.get('new_label', '').strip()
            desc = request.POST.get('new_desc', '').strip()
            if label and desc:
                save_protocol_rule(_slugify(label), label, desc)
        elif 'delete_rule' in request.POST:
            key = request.POST.get('rule_key', '')
            if key:
                delete_protocol_rule(key)
        return redirect('dashboard')

    period = request.GET.get('period', 'all')

    analyses_map = {a.audio_file_id: a for a in get_all_analyses()}
    audios_qs = AudioFile.objects.order_by('-uploaded_at')
    protocol_rules = get_protocol_rules()

    rows = []
    for audio in audios_qs:
        analysis = analyses_map.get(audio.id)
        g = analysis.gemini_analysis if analysis else None
        m = analysis.math_metrics if analysis else None

        agent_pct = client_pct = None
        has_explicit_speakers = False
        if m and g:
            sm = m.speaker_metrics
            agent_ids, client_ids = _resolve_speaker_ids(g, set(sm.keys()))
            if agent_ids and client_ids:
                agent_pct = sum(sm[i].monopoly_percentage for i in agent_ids if i in sm)
                client_pct = sum(sm[i].monopoly_percentage for i in client_ids if i in sm)
                has_explicit_speakers = bool(g.agent_speaker_ids) and bool(g.client_speaker_ids)

        rows.append({
            'id': audio.id,
            'original_name': audio.original_name,
            'uploaded_at': audio.uploaded_at,
            'date': _utc_to_local_date(audio.uploaded_at),
            'total_duration': round(m.total_duration, 1) if m else None,
            'visit_category': g.visit_category if g else None,
            'visit_reason': g.visit_reason if g else None,
            'sentiment': g.overall_sentiment if g else None,
            'fcr': g.fcr if g else None,
            'protocol_score': round(g.protocol.compliance_score * 100, 1) if g else None,
            'interruption_rate': round(m.interruption_rate, 2) if m else None,
            'latency': round(m.avg_reaction_time, 2) if m else None,
            'agent_pct': agent_pct,
            'client_pct': client_pct,
            'has_explicit_speakers': has_explicit_speakers,
            '_steps': g.protocol.steps if g else {},
        })

    # Filter by period
    today = date.today()
    cutoffs = {
        'Hoy': today,
        '7d': today - timedelta(days=6),
        '30d': today - timedelta(days=29),
        'all': None,
    }
    cutoff = cutoffs.get(period)
    filtered = [r for r in rows if cutoff is None or r['date'] >= cutoff]

    # KPIs
    total_calls = len(filtered)
    fcr_vals = [r['fcr'] for r in filtered if r['fcr'] is not None]
    fcr_rate = round(sum(fcr_vals) / len(fcr_vals) * 100, 1) if fcr_vals else 0
    int_vals = [r['interruption_rate'] for r in filtered if r['interruption_rate'] is not None]
    avg_interruptions = round(sum(int_vals) / len(int_vals), 2) if int_vals else 0
    proto_vals = [r['protocol_score'] for r in filtered if r['protocol_score'] is not None]
    avg_protocol = round(sum(proto_vals) / len(proto_vals), 1) if proto_vals else 0

    # ── Charts ──────────────────────────────────────────────────────────────
    fig_monopoly = fig_latency = fig_fcr_trend = fig_categories = fig_protocol_steps = ''

    # Monopolio: solo audios con speakers explícitos, normalizado por audio
    monopoly_rows = [
        r for r in filtered
        if r['has_explicit_speakers']
        and r['agent_pct'] is not None and r['client_pct'] is not None
        and (r['agent_pct'] + r['client_pct']) > 0
    ]
    if monopoly_rows:
        shares = [r['agent_pct'] / (r['agent_pct'] + r['client_pct']) for r in monopoly_rows]
        avg_agent = sum(shares) / len(shares) * 100
        avg_client = 100 - avg_agent
        fig = px.pie(
            pd.DataFrame({'Hablante': ['Agente', 'Cliente'], '% Tiempo': [avg_agent, avg_client]}),
            names='Hablante', values='% Tiempo',
            color_discrete_sequence=[_EM['agent'], _EM['client']], hole=0.45,
        )
        fig.update_traces(
            textinfo='percent+label',
            textfont=dict(family='Inter, system-ui, sans-serif', size=12),
        )
        fig.update_layout(**_base_layout(showlegend=False))
        fig_monopoly = _chart_html(fig)

    # Latencia promedio por fecha
    lat_rows = [(r['date'], r['latency']) for r in filtered if r['latency'] is not None]
    if lat_rows:
        lat_df = (
            pd.DataFrame(lat_rows, columns=['Fecha', 'Latencia (s)'])
            .groupby('Fecha')['Latencia (s)'].mean()
            .reset_index().sort_values('Fecha')
        )
        fig = px.line(
            lat_df, x='Fecha', y='Latencia (s)', markers=True,
            color_discrete_sequence=[_EM['primary']],
        )
        fig.update_traces(line=dict(width=2.5), marker=dict(size=7))
        fig.update_layout(**_base_layout())
        fig_latency = _chart_html(fig)

    # FCR trend por fecha
    fcr_rows = [(r['date'], r['fcr']) for r in filtered if r['fcr'] is not None]
    if fcr_rows:
        fcr_df = (
            pd.DataFrame(fcr_rows, columns=['Fecha', 'FCR'])
            .groupby('Fecha')['FCR'].apply(lambda x: x.mean() * 100)
            .reset_index().rename(columns={'FCR': 'FCR (%)'}).sort_values('Fecha')
        )
        fig = px.area(
            fcr_df, x='Fecha', y='FCR (%)', markers=True,
            color_discrete_sequence=[_EM['primary']], range_y=[0, 105],
        )
        fig.update_traces(
            line=dict(width=2.5),
            marker=dict(size=7),
            fillcolor=_EM['fill'],
        )
        fig.add_hline(
            y=80, line_dash='dot', line_color=_EM['meta'],
            annotation_text='Meta 80%',
            annotation_font=dict(color=_EM['meta'], size=11),
        )
        fig.update_layout(**_base_layout())
        fig_fcr_trend = _chart_html(fig)

    # Distribución por categoría
    cat_vals = [r['visit_category'] for r in filtered if r['visit_category']]
    if cat_vals:
        cat_df = (
            pd.Series(cat_vals).value_counts()
            .reset_index().rename(columns={'index': 'Categoría', 0: 'Cantidad'})
        )
        cat_df.columns = ['Categoría', 'Cantidad']
        fig = px.bar(
            cat_df, x='Categoría', y='Cantidad',
            color='Categoría', text='Cantidad',
            color_discrete_sequence=_EM['categories'],
        )
        fig.update_traces(textposition='outside', marker_line_width=0)
        fig.update_layout(**_base_layout(showlegend=False))
        fig_categories = _chart_html(fig)

    # Cumplimiento por paso de protocolo
    step_totals: dict[str, list[bool]] = {}
    for r in filtered:
        for key, val in r['_steps'].items():
            if key in protocol_rules:  # ignorar pasos eliminados
                step_totals.setdefault(key, []).append(bool(val))

    if step_totals:
        proto_rows = []
        for key, values in step_totals.items():
            label = protocol_rules.get(key, {}).get('label', key)
            proto_rows.append({'Paso': label, '% Cumplimiento': sum(values) / len(values) * 100})
        proto_df = pd.DataFrame(proto_rows).sort_values('% Cumplimiento')
        fig = px.bar(
            proto_df, x='% Cumplimiento', y='Paso', orientation='h',
            color='% Cumplimiento',
            color_continuous_scale=_EM['scale_compliance'],
            range_color=[0, 100],
            text=proto_df['% Cumplimiento'].apply(lambda v: f'{v:.0f}%'),
        )
        fig.update_traces(textposition='outside', marker_line_width=0)
        fig.update_layout(**_base_layout(
            coloraxis_showscale=False,
            margin=dict(t=10, b=10, l=10, r=120),
            xaxis_range=[0, 115],
        ))
        fig_protocol_steps = _chart_html(fig)

    return render(request, 'dashboard.html', {
        'audios': filtered,
        'period': period,
        'total_calls': total_calls,
        'fcr_rate': fcr_rate,
        'avg_interruptions': avg_interruptions,
        'avg_protocol': avg_protocol,
        'fig_monopoly': fig_monopoly,
        'fig_latency': fig_latency,
        'fig_fcr_trend': fig_fcr_trend,
        'fig_categories': fig_categories,
        'fig_protocol_steps': fig_protocol_steps,
        'protocol_rules': protocol_rules,
    })


def detail(request, audio_file_id):
    audio_file = get_object_or_404(AudioFile, id=audio_file_id)
    analysis = get_analysis(audio_file_id)
    protocol_rules = get_protocol_rules()

    fig_monopoly_detail = ''
    protocol_steps = []

    if analysis and analysis.gemini_analysis:
        g = analysis.gemini_analysis
        m = analysis.math_metrics
        sm = m.speaker_metrics

        # Monopoly pie chart
        agent_ids, client_ids = _resolve_speaker_ids(g, set(sm.keys()))
        if agent_ids and client_ids:
            agent_time = sum(sm[i].monopoly_percentage for i in agent_ids if i in sm)
            client_time = sum(sm[i].monopoly_percentage for i in client_ids if i in sm)
            fig = px.pie(
                pd.DataFrame({'Hablante': ['Agente', 'Cliente'], '% Tiempo': [agent_time, client_time]}),
                names='Hablante', values='% Tiempo', hole=0.5,
                color_discrete_sequence=[_EM['agent'], _EM['client']],
                title='Distribución del tiempo en esta atención',
            )
            fig.update_traces(
                textinfo='percent+label',
                textfont=dict(family='Inter, system-ui, sans-serif', size=12),
            )
            fig.update_layout(**_base_layout(
                margin=dict(t=40, b=10, l=10, r=10),
                title_font=dict(family='Inter, system-ui, sans-serif', size=13, color='#6b7280'),
            ))
            fig_monopoly_detail = _chart_html(fig)

        # Protocol checklist with human-readable labels
        for key, result in g.protocol.steps.items():
            label = protocol_rules.get(key, {}).get('label', key)
            protocol_steps.append((label, result))

    return render(request, 'detail.html', {
        'audio_file': audio_file,
        'analysis': analysis,
        'fig_monopoly_detail': fig_monopoly_detail,
        'protocol_steps': protocol_steps,
    })
