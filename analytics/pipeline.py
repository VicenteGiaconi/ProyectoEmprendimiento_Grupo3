"""Orchestrator: reads AudioFile records, runs both analyzers, persists results."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Optional

from .database import get_analysis, get_audio_files, get_protocol_rules, save_analysis
from .deepgram_parser import build_transcript, parse_diarization
from .gemini_client import GeminiClient
from .math_analyzer import analyze as math_analyze
from .models import FullAnalysis

logger = logging.getLogger(__name__)


async def process_record(
    record: dict,
    gemini: GeminiClient,
    protocol_rules: dict[str, dict],
    skip_existing: bool = True,
) -> Optional[FullAnalysis]:
    """Process a single AudioFile dict into a FullAnalysis and persist it."""
    audio_id: int = record["id"]

    existing = get_analysis(audio_id)
    if skip_existing and existing is not None and existing.gemini_analysis is not None:
        logger.info("audio_id=%d already processed — skipping", audio_id)
        return None

    words = parse_diarization(record.get("diarization", []))
    if not words:
        logger.warning("audio_id=%d has no diarization data — skipping", audio_id)
        return None

    # Module 1 — pure-Python math metrics
    math_metrics = math_analyze(words)

    # Module 2 — Gemini semantic analysis
    gemini_result = None
    transcript = build_transcript(words)
    if transcript.strip():
        try:
            gemini_result = await gemini.analyze(transcript, protocol_rules)
        except Exception as exc:
            logger.error("Gemini failed for audio_id=%d: %s", audio_id, exc)

    raw_ts = str(record.get("uploaded_at", ""))
    try:
        uploaded_at = datetime.fromisoformat(raw_ts.replace(" ", "T"))
    except (ValueError, TypeError):
        uploaded_at = datetime.utcnow()

    analysis = FullAnalysis(
        audio_file_id=audio_id,
        original_name=record["original_name"],
        uploaded_at=uploaded_at,
        math_metrics=math_metrics,
        gemini_analysis=gemini_result,
    )
    save_analysis(analysis)
    logger.info("Saved analysis for audio_id=%d", audio_id)
    return analysis


async def run_pipeline(skip_existing: bool = True) -> list[FullAnalysis]:
    """Fetch all completed AudioFile records and run the full analytics pipeline."""
    records = get_audio_files()
    if not records:
        logger.info("No completed audio files found in Django DB.")
        return []

    protocol_rules = get_protocol_rules()
    logger.info(
        "Processing %d audio file(s) with %d protocol rules...",
        len(records), len(protocol_rules),
    )

    gemini = GeminiClient()
    results: list[FullAnalysis] = []

    for record in records:
        result = await process_record(record, gemini, protocol_rules, skip_existing)
        if result:
            results.append(result)

    logger.info("Pipeline complete — %d new analyses saved.", len(results))
    return results


def run() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    asyncio.run(run_pipeline())


if __name__ == "__main__":
    run()
