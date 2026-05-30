"""Generate realistic demo data in analytics.db for testing the Streamlit dashboard.

Usage:
    python seed_demo.py
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta

from analytics.database import save_analysis
from analytics.models import (
    FullAnalysis,
    GeminiAnalysis,
    MathMetrics,
    ProtocolChecklist,
    SpeakerMetrics,
)

random.seed(42)

CATEGORIES = ["Reclamo", "Consulta", "Venta", "Devolución", "Otro"]
SENTIMENTS = ["positivo", "neutral", "negativo"]
VISIT_REASONS = {
    "Reclamo": ["Cargo incorrecto en factura", "Producto defectuoso", "Demora en entrega"],
    "Consulta": ["Consulta de saldo", "Horarios de atención", "Estado de pedido"],
    "Venta": ["Upgrade de plan", "Nuevo producto", "Promoción especial"],
    "Devolución": ["Devolución por garantía", "Producto equivocado recibido"],
    "Otro": ["Cambio de datos personales", "Consulta general"],
}
FCR_JUSTIFICATIONS = {
    True: [
        "El cliente confirmó que el problema fue resuelto durante la llamada.",
        "La solicitud fue procesada satisfactoriamente.",
        "El agente ofreció una solución inmediata y el cliente aceptó.",
    ],
    False: [
        "Se requiere revisión interna, se generó un ticket de seguimiento.",
        "El problema necesita intervención técnica adicional.",
        "El cliente deberá llamar nuevamente en 24–48 horas.",
    ],
}


def make_speaker_metrics(
    agent_pct: float,
    total_duration: float,
) -> dict[int, SpeakerMetrics]:
    client_pct = 100.0 - agent_pct
    agent_time = total_duration * agent_pct / 100
    client_time = total_duration * client_pct / 100
    return {
        0: SpeakerMetrics(
            speaker_id=0,
            total_time=round(agent_time, 3),
            monopoly_percentage=round(agent_pct, 2),
            word_count=int(agent_time * 2.5),  # ~2.5 words/sec
        ),
        1: SpeakerMetrics(
            speaker_id=1,
            total_time=round(client_time, 3),
            monopoly_percentage=round(client_pct, 2),
            word_count=int(client_time * 2.0),
        ),
    }


def make_analysis(idx: int, days_ago: int) -> FullAnalysis:
    category = random.choice(CATEGORIES)
    reason = random.choice(VISIT_REASONS[category])
    fcr = random.random() > 0.35  # ~65% FCR rate
    sentiment = random.choices(SENTIMENTS, weights=[0.4, 0.4, 0.2])[0]

    total_duration = random.uniform(90, 480)  # 1.5 – 8 minutes
    agent_pct = random.uniform(45, 70)        # agent tends to speak more
    interruption_count = random.randint(0, 8)
    interruption_rate = round(interruption_count / (total_duration / 60), 4)
    avg_reaction = round(random.uniform(0.3, 2.5), 3)

    greeted = random.random() > 0.05
    asked_id = random.random() > 0.15
    offered_sol = random.random() > 0.1
    goodbye = random.random() > 0.08
    empathy = random.random() > 0.25

    uploaded_at = datetime.utcnow() - timedelta(
        days=days_ago,
        hours=random.randint(8, 17),
        minutes=random.randint(0, 59),
    )

    return FullAnalysis(
        audio_file_id=idx,
        original_name=f"llamada_{idx:03d}.mp3",
        uploaded_at=uploaded_at,
        math_metrics=MathMetrics(
            interruption_count=interruption_count,
            interruption_rate=interruption_rate,
            speaker_metrics=make_speaker_metrics(agent_pct, total_duration),
            avg_reaction_time=avg_reaction,
            total_duration=round(total_duration, 3),
        ),
        gemini_analysis=GeminiAnalysis(
            visit_reason=reason,
            visit_category=category,
            protocol=ProtocolChecklist(
                greeted=greeted,
                asked_for_id=asked_id,
                offered_solution=offered_sol,
                said_goodbye=goodbye,
                empathy_shown=empathy,
            ),
            fcr=fcr,
            fcr_justification=random.choice(FCR_JUSTIFICATIONS[fcr]),
            overall_sentiment=sentiment,
        ),
        processed_at=uploaded_at + timedelta(seconds=random.randint(5, 30)),
    )


def main() -> None:
    analyses = [make_analysis(i + 1, days_ago=random.randint(0, 29)) for i in range(30)]
    for a in analyses:
        save_analysis(a)
    print(f"Seeded {len(analyses)} demo analyses into analytics.db")


if __name__ == "__main__":
    main()
