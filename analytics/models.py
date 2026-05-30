from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class Word(BaseModel):
    word: str
    start: float
    end: float
    confidence: float = 1.0
    speaker: int


class Utterance(BaseModel):
    text: str
    start: float
    end: float
    speaker: int


class SpeakerMetrics(BaseModel):
    speaker_id: int
    total_time: float
    monopoly_percentage: float
    word_count: int


class MathMetrics(BaseModel):
    interruption_count: int
    interruption_rate: float
    speaker_metrics: dict[int, SpeakerMetrics]
    avg_reaction_time: float
    total_duration: float


class ProtocolChecklist(BaseModel):
    steps: dict[str, bool] = Field(default_factory=dict)

    @property
    def compliance_score(self) -> float:
        if not self.steps:
            return 0.0
        return sum(self.steps.values()) / len(self.steps)

    @classmethod
    def from_dict(cls, data: dict) -> "ProtocolChecklist":
        """Handles both new format {steps: {...}} and legacy flat format {greeted: true, ...}."""
        if "steps" in data:
            return cls(steps=data["steps"])
        return cls(steps={k: bool(v) for k, v in data.items() if isinstance(v, bool)})


class GeminiAnalysis(BaseModel):
    visit_reason: str
    visit_category: str
    protocol: ProtocolChecklist
    fcr: bool
    fcr_justification: str
    overall_sentiment: Optional[str] = None
    agent_speaker_ids: list[int] = Field(default_factory=list)
    client_speaker_ids: list[int] = Field(default_factory=list)


class FullAnalysis(BaseModel):
    audio_file_id: int
    original_name: str
    uploaded_at: datetime
    math_metrics: MathMetrics
    gemini_analysis: Optional[GeminiAnalysis] = None
    processed_at: datetime = Field(default_factory=datetime.utcnow)
