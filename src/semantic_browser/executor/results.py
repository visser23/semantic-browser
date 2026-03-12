"""Result classification."""

from __future__ import annotations

from semantic_browser.models import ExecutionResult, Observation, ObservationDelta, StepStatus


def classify_status(ok: bool, message: str, delta: ObservationDelta) -> StepStatus:
    msg = (message or "").lower()
    if not ok:
        return "failed"
    if msg in {"waited", "went back", "went forward", "reloaded", "navigated"}:
        return "success"
    if delta.added_blockers:
        return "blocked"
    if delta.navigated or delta.changed_values or delta.changed_regions or delta.materiality != "minor":
        return "success"
    if "not found" in msg:
        return "stale"
    return "ambiguous"


def _effect_from_delta(delta: ObservationDelta, effect_hint: str | None) -> str:
    if effect_hint in {"navigation", "state_change", "content_change", "none"}:
        return effect_hint
    if delta.navigated:
        return "navigation"
    if delta.content_state_changes:
        return "content_change"
    if (
        delta.changed_values
        or delta.interaction_state_changes
        or delta.workflow_state_changes
        or delta.changed_regions
    ):
        return "state_change"
    return "none"


def build_execution(
    op: str,
    ok: bool,
    message: str,
    before: Observation,
    after: Observation,
    delta: ObservationDelta,
    *,
    effect_hint: str | None = None,
    evidence: dict[str, object] | None = None,
) -> ExecutionResult:
    effect = _effect_from_delta(delta, effect_hint)
    return ExecutionResult(
        op=op,
        ok=ok,
        message=message,
        caused_navigation=effect == "navigation",
        caused_value_change=op in {"fill", "clear", "select_option", "toggle"},
        caused_modal_change=any(b.kind == "modal" for b in after.blockers)
        != any(b.kind == "modal" for b in before.blockers),
        effect=effect,  # type: ignore[arg-type]
        evidence=evidence or {},
    )
