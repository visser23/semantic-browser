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
    if delta.navigated or delta.changed_values or delta.changed_regions:
        return "success"
    if "not found" in msg:
        return "stale"
    return "ambiguous"


def build_execution(op: str, ok: bool, message: str, observation: Observation) -> ExecutionResult:
    return ExecutionResult(
        op=op,
        ok=ok,
        message=message,
        caused_navigation=observation.page.url != "",
        caused_value_change=op in {"fill", "clear", "select_option", "toggle"},
        caused_modal_change=any(b.kind == "modal" for b in observation.blockers),
    )
