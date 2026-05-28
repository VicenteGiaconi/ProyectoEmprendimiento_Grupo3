"""Module 1 – Pure-Python mathematical metrics extracted from Deepgram diarization."""

from __future__ import annotations

from .models import MathMetrics, SpeakerMetrics, Word


def _calculate_interruptions(words: list[Word]) -> tuple[int, float]:
    """Detect overlaps: word from speaker B starts before speaker A's word ends.

    Returns (count, rate_per_minute).
    """
    if len(words) < 2:
        return 0, 0.0

    count = 0
    for i in range(1, len(words)):
        prev, curr = words[i - 1], words[i]
        if curr.speaker != prev.speaker and curr.start < prev.end:
            count += 1

    duration = words[-1].end - words[0].start
    rate = (count / duration * 60.0) if duration > 0 else 0.0
    return count, round(rate, 4)


def _calculate_monopoly(words: list[Word]) -> dict[int, SpeakerMetrics]:
    """Sum speech duration per speaker and express as a share of total."""
    if not words:
        return {}

    times: dict[int, float] = {}
    counts: dict[int, int] = {}
    for w in words:
        duration = w.end - w.start
        times[w.speaker] = times.get(w.speaker, 0.0) + duration
        counts[w.speaker] = counts.get(w.speaker, 0) + 1

    total = sum(times.values())
    return {
        sid: SpeakerMetrics(
            speaker_id=sid,
            total_time=round(t, 3),
            monopoly_percentage=round((t / total * 100) if total > 0 else 0.0, 2),
            word_count=counts.get(sid, 0),
        )
        for sid, t in times.items()
    }


def _calculate_reaction_time(words: list[Word]) -> float:
    """Mean silence gap (seconds) between consecutive speaker turns.

    Only positive gaps are included; overlaps (negative gaps) are excluded.
    """
    if len(words) < 2:
        return 0.0

    gaps: list[float] = []
    for i in range(1, len(words)):
        prev, curr = words[i - 1], words[i]
        if curr.speaker != prev.speaker:
            gap = curr.start - prev.end
            if gap > 0:
                gaps.append(gap)

    return round(sum(gaps) / len(gaps), 3) if gaps else 0.0


def analyze(words: list[Word]) -> MathMetrics:
    """Run all mathematical metrics and return a MathMetrics instance.

    Handles gracefully the edge case of single-speaker audio (no diarization).
    """
    if not words:
        return MathMetrics(
            interruption_count=0,
            interruption_rate=0.0,
            speaker_metrics={},
            avg_reaction_time=0.0,
            total_duration=0.0,
        )

    interruption_count, interruption_rate = _calculate_interruptions(words)
    speaker_metrics = _calculate_monopoly(words)
    avg_reaction_time = _calculate_reaction_time(words)
    total_duration = round(words[-1].end - words[0].start, 3)

    return MathMetrics(
        interruption_count=interruption_count,
        interruption_rate=interruption_rate,
        speaker_metrics=speaker_metrics,
        avg_reaction_time=avg_reaction_time,
        total_duration=total_duration,
    )
