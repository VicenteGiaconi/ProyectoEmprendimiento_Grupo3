"""Module 2 – Semantic analysis via Google Gemini API (google-genai SDK)."""

from __future__ import annotations

import json
import logging
from typing import Optional

from google import genai
from google.genai import types

from .config import GEMINI_API_KEY
from .models import GeminiAnalysis, ProtocolChecklist

logger = logging.getLogger(__name__)

_MODEL = "gemini-3.5-flash"


def _build_config(protocol_rules: dict[str, dict]) -> types.GenerateContentConfig:
    """Build the Gemini request config with a protocol-aware system prompt."""
    schema_fields = "\n".join(
        f'    "{key}": true/false,' for key in protocol_rules
    )
    rules_list = "\n".join(
        f'- {key}: {info["description"]}' for key, info in protocol_rules.items()
    )
    system_prompt = (
        "Eres un sistema experto en análisis de calidad de atención al cliente. "
        "Analiza la transcripción de una llamada entre un Agente y un Cliente.\n\n"
        "Debes devolver ÚNICAMENTE un objeto JSON válido con la siguiente estructura exacta:\n"
        "{\n"
        '  "visit_reason": "descripción corta del motivo de la visita/llamada",\n'
        '  "visit_category": "uno de: Reclamo, Consulta, Venta, Devolución, Otro",\n'
        '  "protocol": {\n'
        f"{schema_fields}\n"
        "  },\n"
        '  "fcr": true/false,\n'
        '  "fcr_justification": "breve justificación de si el problema fue resuelto en esta llamada",\n'
        '  "overall_sentiment": "positivo/neutral/negativo"\n'
        "}\n\n"
        "Pasos de protocolo a evaluar:\n"
        f"{rules_list}\n\n"
        "Responde SOLO con el JSON. Sin markdown, sin texto adicional."
    )
    return types.GenerateContentConfig(
        response_mime_type="application/json",
        temperature=0.1,
        system_instruction=system_prompt,
    )


def _parse_response(text: str, protocol_rules: dict[str, dict]) -> GeminiAnalysis:
    try:
        data: dict = json.loads(text.strip())
    except json.JSONDecodeError as exc:
        logger.error("Gemini returned invalid JSON: %s", exc)
        raise

    try:
        # Build steps dict only for keys that Gemini actually returned
        raw_protocol: dict = data.get("protocol", {})
        steps = {k: bool(raw_protocol[k]) for k in protocol_rules if k in raw_protocol}

        return GeminiAnalysis(
            visit_reason=data["visit_reason"],
            visit_category=data["visit_category"],
            protocol=ProtocolChecklist(steps=steps),
            fcr=bool(data["fcr"]),
            fcr_justification=data["fcr_justification"],
            overall_sentiment=data.get("overall_sentiment"),
        )
    except KeyError as exc:
        logger.error("Missing key in Gemini response: %s", exc)
        raise


class GeminiClient:
    def __init__(self, api_key: Optional[str] = None) -> None:
        key = api_key or GEMINI_API_KEY
        if not key:
            raise ValueError(
                "GEMINI_API_KEY is not set. Add it to your .env file."
            )
        self._client = genai.Client(api_key=key)

    def analyze_sync(
        self, transcript: str, protocol_rules: dict[str, dict]
    ) -> GeminiAnalysis:
        config = _build_config(protocol_rules)
        response = self._client.models.generate_content(
            model=_MODEL,
            contents=f"Transcripción de la llamada:\n\n{transcript}",
            config=config,
        )
        logger.info("Gemini analysis completed with model %s", _MODEL)
        return _parse_response(response.text, protocol_rules)

    async def analyze(
        self, transcript: str, protocol_rules: dict[str, dict]
    ) -> GeminiAnalysis:
        config = _build_config(protocol_rules)
        response = await self._client.aio.models.generate_content(
            model=_MODEL,
            contents=f"Transcripción de la llamada:\n\n{transcript}",
            config=config,
        )
        logger.info("Gemini analysis completed with model %s", _MODEL)
        return _parse_response(response.text, protocol_rules)
