"""Pydantic models for external contracts."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field


ObservationMode = Literal["summary", "full", "delta", "debug", "auto"]
StepStatus = Literal["success", "failed", "blocked", "stale", "invalid", "ambiguous"]


def utc_now() -> datetime:
    return datetime.now(tz=timezone.utc)


class WarningNotice(BaseModel):
    kind: str
    description: str
    severity: Literal["low", "medium", "high"] = "low"


class Blocker(BaseModel):
    kind: str
    severity: Literal["low", "medium", "high"]
    description: str
    related_action_ids: list[str] = Field(default_factory=list)


class PageInfo(BaseModel):
    url: str
    title: str
    domain: str
    page_type: str
    page_identity: str
    ready_state: str
    modal_active: bool
    frame_count: int
    profile_name: str | None = None


class PageSummary(BaseModel):
    headline: str
    key_points: list[str] = Field(default_factory=list)


class RegionSummary(BaseModel):
    id: str
    kind: str
    name: str
    frame_id: str
    order: int
    visible: bool
    in_viewport: bool
    interactable_count: int
    content_item_count: int
    primary_action_ids: list[str]
    preview_text: str | None = None


class FormSummary(BaseModel):
    id: str
    name: str
    frame_id: str
    field_ids: list[str]
    submit_action_ids: list[str]
    validity: str
    required_missing: list[str]


class ContentItemPreview(BaseModel):
    id: str
    title: str | None = None
    subtitle: str | None = None
    badges: list[str] = Field(default_factory=list)
    key_values: dict[str, str] = Field(default_factory=dict)
    open_action_id: str | None = None
    secondary_action_ids: list[str] = Field(default_factory=list)


class ContentGroupSummary(BaseModel):
    id: str
    kind: str
    name: str
    item_count: int | None = None
    visible_item_count: int | None = None
    preview_items: list[ContentItemPreview] = Field(default_factory=list)
    inspect_action_id: str | None = None


class ActionDescriptor(BaseModel):
    id: str
    op: str
    label: str
    target_id: str | None = None
    region_id: str | None = None
    enabled: bool = True
    requires_value: bool = False
    value_schema: dict[str, Any] | None = None
    destructive: bool = False
    navigational: bool = False
    primary: bool = False
    confidence: float = 0.8
    locator_recipe: dict[str, Any] = Field(default_factory=dict)


class ObservationMetrics(BaseModel):
    extraction_ms: int = 0
    action_count: int = 0
    interactable_count: int = 0
    region_count: int = 0
    form_count: int = 0
    content_group_count: int = 0
    delta_bytes: int = 0
    full_bytes: int = 0
    extraction_route: str | None = None
    aria_quality: float | None = None
    scoped_interactable_count: int | None = None
    total_interactable_count: int | None = None


class ConfidenceReport(BaseModel):
    overall: float = 0.8
    extraction: float = 0.8
    grouping: float = 0.8
    actionability: float = 0.8
    stability: float = 0.8
    reasons: list[str] = Field(default_factory=list)


class ObservationDelta(BaseModel):
    changed_values: dict[str, Any] = Field(default_factory=dict)
    added_blockers: list[Blocker] = Field(default_factory=list)
    removed_blocker_kinds: list[str] = Field(default_factory=list)
    enabled_actions: list[str] = Field(default_factory=list)
    disabled_actions: list[str] = Field(default_factory=list)
    changed_regions: list[str] = Field(default_factory=list)
    page_identity_changed: bool = False
    navigated: bool = False
    notes: list[str] = Field(default_factory=list)


class Observation(BaseModel):
    session_id: str
    timestamp: datetime = Field(default_factory=utc_now)
    mode: ObservationMode
    page: PageInfo
    summary: PageSummary
    blockers: list[Blocker] = Field(default_factory=list)
    warnings: list[WarningNotice] = Field(default_factory=list)
    regions: list[RegionSummary] = Field(default_factory=list)
    forms: list[FormSummary] = Field(default_factory=list)
    content_groups: list[ContentGroupSummary] = Field(default_factory=list)
    available_actions: list[ActionDescriptor] = Field(default_factory=list)
    metrics: ObservationMetrics = Field(default_factory=ObservationMetrics)
    confidence: ConfidenceReport = Field(default_factory=ConfidenceReport)


class ActionRequest(BaseModel):
    action_id: str | None = None
    op: str | None = None
    target_id: str | None = None
    value: Any | None = None
    options: dict[str, Any] = Field(default_factory=dict)
    expectation: str | None = None


class ExecutionResult(BaseModel):
    op: str
    ok: bool
    started_at: datetime = Field(default_factory=utc_now)
    ended_at: datetime = Field(default_factory=utc_now)
    message: str | None = None
    caused_navigation: bool = False
    caused_modal_change: bool = False
    caused_value_change: bool = False


class StepResult(BaseModel):
    request: ActionRequest
    status: StepStatus
    message: str | None = None
    execution: ExecutionResult
    observation: Observation
    delta: ObservationDelta | None = None


class DiagnosticsReport(BaseModel):
    session_id: str
    managed: bool
    attached_kind: str
    current_url: str
    last_observation_at: datetime | None = None
    trace_events: int = 0
    healthy: bool = True
    notes: list[str] = Field(default_factory=list)
