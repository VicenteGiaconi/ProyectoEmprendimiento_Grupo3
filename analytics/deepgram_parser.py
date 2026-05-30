from __future__ import annotations

from typing import Optional

from .models import Utterance, Word


def parse_diarization(diarization_json: list[dict]) -> list[Word]:
    """Parse the raw Deepgram diarization list into typed Word objects.

    Silently skips any malformed entries so a partial result is still usable.
    """
    words: list[Word] = []
    for item in diarization_json:
        try:
            words.append(
                Word(
                    word=item["word"],
                    start=float(item["start"]),
                    end=float(item["end"]),
                    confidence=float(item.get("confidence", 1.0)),
                    speaker=int(item["speaker"]),
                )
            )
        except (KeyError, ValueError, TypeError):
            continue
    return sorted(words, key=lambda w: w.start)


def group_utterances(words: list[Word]) -> list[Utterance]:
    """Merge consecutive words from the same speaker into utterances."""
    if not words:
        return []

    utterances: list[Utterance] = []
    current: list[Word] = [words[0]]

    for word in words[1:]:
        if word.speaker == current[-1].speaker:
            current.append(word)
        else:
            utterances.append(
                Utterance(
                    text=" ".join(w.word for w in current),
                    start=current[0].start,
                    end=current[-1].end,
                    speaker=current[0].speaker,
                )
            )
            current = [word]

    utterances.append(
        Utterance(
            text=" ".join(w.word for w in current),
            start=current[0].start,
            end=current[-1].end,
            speaker=current[0].speaker,
        )
    )
    return utterances


def build_transcript(
    words: list[Word],
    speaker_names: Optional[dict[int, str]] = None,
) -> str:
    """Build a labelled transcript string ready to send to Gemini."""
    if speaker_names is None:
        unique_ids = sorted({w.speaker for w in words})
        speaker_names = {sid: f"Interlocutor {sid}" for sid in unique_ids}

    lines: list[str] = []
    for utt in group_utterances(words):
        label = speaker_names.get(utt.speaker, f"Speaker {utt.speaker}")
        lines.append(f"{label}: {utt.text}")
    return "\n".join(lines)
