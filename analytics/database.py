"""SQLite persistence layer.

Read-only access to Django's db.sqlite3 for AudioFile records.
Read-write access to analytics.db for FullAnalysis results and protocol rules.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime
from typing import Optional

from .config import (
    ANALYTICS_DB_PATH,
    DJANGO_DB_PATH,
    PROTOCOL_RULE_LABELS,
    PROTOCOL_RULES,
)
from .models import (
    FullAnalysis,
    GeminiAnalysis,
    MathMetrics,
    ProtocolChecklist,
    SpeakerMetrics,
)

logger = logging.getLogger(__name__)


# ─────────────────── Django DB (read-only) ───────────────────

def get_audio_files() -> list[dict]:
    """Return all completed AudioFile rows from the Django SQLite database."""
    try:
        conn = sqlite3.connect(f"file:{DJANGO_DB_PATH}?mode=ro", uri=True)
    except sqlite3.OperationalError as exc:
        logger.error("Cannot open Django DB at %s: %s", DJANGO_DB_PATH, exc)
        return []

    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT id, original_name, uploaded_at, diarization, sentiment, transcription
            FROM audio_upload_audiofile
            WHERE transcription_status = 'completed'
            ORDER BY uploaded_at DESC
            """
        ).fetchall()
        return [
            {
                "id": row["id"],
                "original_name": row["original_name"],
                "uploaded_at": row["uploaded_at"],
                "diarization": json.loads(row["diarization"] or "[]"),
                "sentiment": json.loads(row["sentiment"] or "{}"),
                "transcription": row["transcription"] or "",
            }
            for row in rows
        ]
    except sqlite3.OperationalError as exc:
        logger.error("Query failed: %s", exc)
        return []
    finally:
        conn.close()


# ─────────────────── Analytics DB — schema ───────────────────

def _init_db() -> None:
    conn = sqlite3.connect(ANALYTICS_DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS analyses (
            audio_file_id INTEGER PRIMARY KEY,
            original_name TEXT    NOT NULL,
            uploaded_at   TEXT    NOT NULL,
            math_metrics  TEXT    NOT NULL,
            gemini_analysis TEXT,
            processed_at  TEXT    NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS protocol_rules (
            key         TEXT PRIMARY KEY,
            label       TEXT NOT NULL,
            description TEXT NOT NULL,
            position    INTEGER DEFAULT 0
        )
        """
    )
    conn.commit()
    conn.close()


def _seed_default_rules(conn: sqlite3.Connection) -> None:
    """Insert the default rules from config.py if the table is empty."""
    for i, (key, description) in enumerate(PROTOCOL_RULES.items()):
        label = PROTOCOL_RULE_LABELS.get(key, key)
        conn.execute(
            "INSERT OR IGNORE INTO protocol_rules (key, label, description, position) VALUES (?, ?, ?, ?)",
            (key, label, description, i),
        )


# ─────────────────── Protocol rules CRUD ───────────────────

def get_protocol_rules() -> dict[str, dict]:
    """Return {key: {label, description}} ordered by position.

    Seeds defaults on first call if the table is empty.
    """
    _init_db()
    conn = sqlite3.connect(ANALYTICS_DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT key, label, description FROM protocol_rules ORDER BY position"
        ).fetchall()
        if not rows:
            _seed_default_rules(conn)
            conn.commit()
            rows = conn.execute(
                "SELECT key, label, description FROM protocol_rules ORDER BY position"
            ).fetchall()
        return {r["key"]: {"label": r["label"], "description": r["description"]} for r in rows}
    finally:
        conn.close()


def save_protocol_rule(key: str, label: str, description: str) -> None:
    """Insert or replace a protocol rule."""
    _init_db()
    conn = sqlite3.connect(ANALYTICS_DB_PATH)
    try:
        conn.execute(
            """
            INSERT INTO protocol_rules (key, label, description, position)
            VALUES (?, ?, ?, (SELECT COALESCE(MAX(position), -1) + 1 FROM protocol_rules))
            ON CONFLICT(key) DO UPDATE SET label=excluded.label, description=excluded.description
            """,
            (key, label, description),
        )
        conn.commit()
    finally:
        conn.close()


def delete_protocol_rule(key: str) -> None:
    """Delete a protocol rule by key."""
    _init_db()
    conn = sqlite3.connect(ANALYTICS_DB_PATH)
    try:
        conn.execute("DELETE FROM protocol_rules WHERE key = ?", (key,))
        conn.commit()
    finally:
        conn.close()


def reorder_protocol_rules(ordered_keys: list[str]) -> None:
    """Update position values to match the given key order."""
    _init_db()
    conn = sqlite3.connect(ANALYTICS_DB_PATH)
    try:
        for i, key in enumerate(ordered_keys):
            conn.execute(
                "UPDATE protocol_rules SET position = ? WHERE key = ?", (i, key)
            )
        conn.commit()
    finally:
        conn.close()


# ─────────────────── Analyses CRUD ───────────────────

def save_analysis(analysis: FullAnalysis) -> None:
    _init_db()
    conn = sqlite3.connect(ANALYTICS_DB_PATH)
    try:
        conn.execute(
            """
            INSERT OR REPLACE INTO analyses
                (audio_file_id, original_name, uploaded_at,
                 math_metrics, gemini_analysis, processed_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                analysis.audio_file_id,
                analysis.original_name,
                analysis.uploaded_at.isoformat(),
                analysis.math_metrics.model_dump_json(),
                analysis.gemini_analysis.model_dump_json()
                if analysis.gemini_analysis
                else None,
                analysis.processed_at.isoformat(),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def _row_to_full_analysis(row: sqlite3.Row) -> Optional[FullAnalysis]:
    try:
        math_raw = json.loads(row["math_metrics"])
        math_raw["speaker_metrics"] = {
            int(k): SpeakerMetrics(**v)
            for k, v in math_raw["speaker_metrics"].items()
        }
        math_metrics = MathMetrics(**math_raw)

        gemini = None
        if row["gemini_analysis"]:
            g = json.loads(row["gemini_analysis"])
            # Support both new {steps: {...}} and legacy flat {greeted: true, ...} format
            g["protocol"] = ProtocolChecklist.from_dict(g["protocol"])
            gemini = GeminiAnalysis(**g)

        return FullAnalysis(
            audio_file_id=row["audio_file_id"],
            original_name=row["original_name"],
            uploaded_at=datetime.fromisoformat(row["uploaded_at"]),
            math_metrics=math_metrics,
            gemini_analysis=gemini,
            processed_at=datetime.fromisoformat(row["processed_at"]),
        )
    except Exception as exc:
        logger.warning("Skipping malformed row id=%s: %s", dict(row).get("audio_file_id"), exc)
        return None


def get_all_analyses() -> list[FullAnalysis]:
    _init_db()
    conn = sqlite3.connect(ANALYTICS_DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT * FROM analyses ORDER BY uploaded_at DESC"
        ).fetchall()
        return [a for row in rows if (a := _row_to_full_analysis(row)) is not None]
    finally:
        conn.close()


def get_analysis(audio_file_id: int) -> Optional[FullAnalysis]:
    _init_db()
    conn = sqlite3.connect(ANALYTICS_DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            "SELECT * FROM analyses WHERE audio_file_id = ?", (audio_file_id,)
        ).fetchone()
        return _row_to_full_analysis(row) if row else None
    finally:
        conn.close()
