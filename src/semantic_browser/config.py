"""Runtime configuration models."""

from __future__ import annotations

from pydantic import BaseModel, Field


class SettleConfig(BaseModel):
    ready_states: list[str] = Field(default_factory=lambda: ["interactive", "complete"])
    mutation_quiet_ms: int = 300
    interactable_stable_ms: int = 200
    layout_stable_ms: int = 150
    max_settle_ms: int = 15000


class ExtractionConfig(BaseModel):
    include_frames: bool = True
    max_elements: int = 2000
    content_group_min_items: int = 3
    low_name_threshold: float = 0.5
    low_action_coverage_threshold: float = 0.3
    summary_top_scope_enabled: bool = True
    summary_top_scope_multiplier: float = 1.6


class RedactionConfig(BaseModel):
    enabled: bool = True
    expose_secrets: bool = False


class TelemetryConfig(BaseModel):
    enabled: bool = True
    trace_dir: str | None = None
    max_events: int = 1000


class RuntimeConfig(BaseModel):
    settle: SettleConfig = Field(default_factory=SettleConfig)
    extraction: ExtractionConfig = Field(default_factory=ExtractionConfig)
    redaction: RedactionConfig = Field(default_factory=RedactionConfig)
    telemetry: TelemetryConfig = Field(default_factory=TelemetryConfig)
