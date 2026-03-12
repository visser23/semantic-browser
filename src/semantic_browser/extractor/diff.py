"""Observation delta computation."""

from __future__ import annotations

from semantic_browser.models import Observation, ObservationDelta


def _materiality_score(delta: ObservationDelta) -> int:
    score = 0
    if delta.navigated:
        score += 4
    score += min(2, len(delta.added_blockers))
    score += min(2, len(delta.content_state_changes))
    score += min(2, len(delta.workflow_state_changes))
    score += min(2, len(delta.interaction_state_changes))
    if abs(delta.confidence_drift) >= 0.2:
        score += 1
    if delta.page_identity_changed:
        score += 1
    return score


def _materiality_label(score: int) -> str:
    if score >= 5:
        return "major"
    if score >= 2:
        return "moderate"
    return "minor"


def build_delta(previous: Observation | None, current: Observation) -> ObservationDelta:
    if previous is None:
        return ObservationDelta(
            changed_values={"initial_observation": True},
            page_identity_changed=False,
            navigated=False,
            materiality="minor",
            notes=["Initial observation"],
        )

    prev_actions = {a.id: a for a in previous.available_actions}
    curr_actions = {a.id: a for a in current.available_actions}
    enabled_actions = [aid for aid, a in curr_actions.items() if a.enabled and not prev_actions.get(aid, a).enabled]
    disabled_actions = [aid for aid, a in curr_actions.items() if not a.enabled and prev_actions.get(aid, a).enabled]

    prev_blocker_kinds = {b.kind for b in previous.blockers}
    curr_blockers = {b.kind: b for b in current.blockers}
    added_blockers = [b for k, b in curr_blockers.items() if k not in prev_blocker_kinds]
    removed_blocker_kinds = [k for k in prev_blocker_kinds if k not in curr_blockers]

    prev_region_ids = {r.id for r in previous.regions}
    curr_region_ids = {r.id for r in current.regions}
    changed_regions = sorted(list(prev_region_ids.symmetric_difference(curr_region_ids)))

    page_identity_changed = previous.page.page_identity != current.page.page_identity
    navigated = previous.page.url != current.page.url
    interaction_state_changes: list[str] = []
    content_state_changes: list[str] = []
    workflow_state_changes: list[str] = []
    reliability_state_changes: list[str] = []
    classification_state_changes: list[str] = []

    prev_forms = {f.id: f for f in previous.forms}
    curr_forms = {f.id: f for f in current.forms}
    for fid, cform in curr_forms.items():
        pform = prev_forms.get(fid)
        if pform is None:
            workflow_state_changes.append(f"form_added:{fid}")
            continue
        if pform.validity != cform.validity:
            workflow_state_changes.append(f"form_validity:{fid}:{pform.validity}->{cform.validity}")
        if pform.required_missing != cform.required_missing:
            workflow_state_changes.append(f"required_missing:{fid}")
    for fid in prev_forms:
        if fid not in curr_forms:
            workflow_state_changes.append(f"form_removed:{fid}")

    prev_groups = {g.id: g for g in previous.content_groups}
    curr_groups = {g.id: g for g in current.content_groups}
    for gid, cgroup in curr_groups.items():
        pgroup = prev_groups.get(gid)
        if pgroup is None:
            content_state_changes.append(f"group_added:{gid}")
            continue
        if (pgroup.item_count or 0) != (cgroup.item_count or 0):
            content_state_changes.append(f"group_count:{gid}:{pgroup.item_count}->{cgroup.item_count}")
        prev_title = pgroup.preview_items[0].title if pgroup.preview_items else None
        curr_title = cgroup.preview_items[0].title if cgroup.preview_items else None
        if prev_title != curr_title:
            content_state_changes.append(f"group_preview:{gid}")
    for gid in prev_groups:
        if gid not in curr_groups:
            content_state_changes.append(f"group_removed:{gid}")

    if previous.page.page_type != current.page.page_type:
        classification_state_changes.append(f"page_type:{previous.page.page_type}->{current.page.page_type}")
    if page_identity_changed:
        classification_state_changes.append("page_identity_refined")

    confidence_drift = round(current.confidence.overall - previous.confidence.overall, 3)
    if abs(confidence_drift) >= 0.05:
        reliability_state_changes.append(f"confidence_drift:{confidence_drift:+.3f}")

    prev_warning_kinds = {w.kind for w in previous.warnings}
    curr_warning_kinds = {w.kind for w in current.warnings}
    for kind in sorted(curr_warning_kinds - prev_warning_kinds):
        reliability_state_changes.append(f"warning_added:{kind}")
    for kind in sorted(prev_warning_kinds - curr_warning_kinds):
        reliability_state_changes.append(f"warning_removed:{kind}")

    if previous.page.modal_active != current.page.modal_active:
        workflow_state_changes.append(
            f"dialog_stack:{'active' if current.page.modal_active else 'cleared'}"
        )

    if enabled_actions:
        interaction_state_changes.append(f"enabled_actions:{len(enabled_actions)}")
    if disabled_actions:
        interaction_state_changes.append(f"disabled_actions:{len(disabled_actions)}")
    if changed_regions:
        interaction_state_changes.append(f"changed_regions:{len(changed_regions)}")

    notes: list[str] = []
    if navigated:
        notes.append("Navigation detected")
    if workflow_state_changes:
        notes.append(f"Workflow updates: {len(workflow_state_changes)}")
    if content_state_changes:
        notes.append(f"Content updates: {len(content_state_changes)}")
    if reliability_state_changes:
        notes.append(f"Reliability updates: {len(reliability_state_changes)}")

    semantic_coverage_change = round(
        (current.metrics.action_count / max(current.metrics.interactable_count, 1))
        - (previous.metrics.action_count / max(previous.metrics.interactable_count, 1)),
        3,
    )

    changed_values: dict[str, object] = {"url": current.page.url} if navigated else {}
    if confidence_drift:
        changed_values["confidence_overall"] = current.confidence.overall

    delta = ObservationDelta(
        changed_values=changed_values,
        added_blockers=added_blockers,
        removed_blocker_kinds=removed_blocker_kinds,
        enabled_actions=enabled_actions,
        disabled_actions=disabled_actions,
        changed_regions=changed_regions,
        page_identity_changed=page_identity_changed,
        navigated=navigated,
        interaction_state_changes=interaction_state_changes,
        content_state_changes=content_state_changes,
        workflow_state_changes=workflow_state_changes,
        reliability_state_changes=reliability_state_changes,
        classification_state_changes=classification_state_changes,
        confidence_drift=confidence_drift,
        semantic_coverage_change=semantic_coverage_change,
        instability_warnings=[c for c in reliability_state_changes if c.startswith("warning_added:")],
        notes=notes,
    )
    delta.materiality = _materiality_label(_materiality_score(delta))  # type: ignore[assignment]
    return delta
