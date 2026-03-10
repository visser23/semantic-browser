"""Extraction orchestrator."""

from __future__ import annotations

import json
import time
from typing import Any

from semantic_browser.config import RuntimeConfig
from semantic_browser.models import (
    ActionDescriptor,
    Observation,
    ObservationMetrics,
    PageSummary,
)

from .blockers import confidence_from_nodes, detect_blockers
from .classifier import classify_page
from .diff import build_delta
from .dom_snapshot import capture_dom_stats
from .grouping import build_content_groups, build_forms, build_regions
from .ids import assign_node_ids, fingerprint_for
from .page_state import capture_page_info
from .redaction import redact_nodes
from .semantics import extract_semantics


def _action_for_node(node: dict[str, Any], node_id: str, idx: int) -> ActionDescriptor | None:
    role = node.get("role", "")
    tag = node.get("tag", "")
    name = (node.get("name") or "").strip() or f"{tag}-{idx}"
    disabled = bool(node.get("disabled", False))
    op = None
    requires_value = False
    if tag in {"input", "textarea"} or role in {"textbox"}:
        if node.get("type") in {"checkbox", "radio"} or role == "checkbox":
            op = "toggle"
        else:
            op = "fill"
            requires_value = True
    elif tag == "select":
        op = "select_option"
        requires_value = True
    elif tag == "a" or role == "link":
        op = "open"
    elif tag == "button" or role in {"button"}:
        op = "click"
    if not op:
        return None
    return ActionDescriptor(
        id=f"act-{idx}-{fingerprint_for(node)[:6]}",
        op=op,
        label=name,
        target_id=node_id,
        enabled=not disabled,
        requires_value=requires_value,
        navigational=op in {"open"},
        confidence=0.85,
        locator_recipe={"name": name, "role": role, "tag": tag},
    )


async def observe_page(
    *,
    session_id: str,
    page: Any,
    mode: str,
    config: RuntimeConfig,
    previous_observation: Observation | None,
    previous_ids: dict[str, str] | None,
) -> tuple[Observation, dict[str, str]]:
    start = time.perf_counter()
    sem = await extract_semantics(page)
    nodes = redact_nodes(sem.get("nodes", []), config.redaction)
    id_map = assign_node_ids(nodes, previous=previous_ids)
    page_info = await capture_page_info(page)
    page_info.page_type = classify_page(nodes)

    actions: list[ActionDescriptor] = [
        ActionDescriptor(
            id="act-global-back",
            op="back",
            label="Back",
            enabled=True,
            navigational=True,
            confidence=0.9,
        ),
        ActionDescriptor(
            id="act-global-forward",
            op="forward",
            label="Forward",
            enabled=True,
            navigational=True,
            confidence=0.9,
        ),
        ActionDescriptor(
            id="act-global-reload",
            op="reload",
            label="Reload",
            enabled=True,
            navigational=True,
            confidence=0.9,
        ),
        ActionDescriptor(
            id="act-global-wait",
            op="wait",
            label="Wait",
            enabled=True,
            requires_value=True,
            value_schema={"type": "integer", "description": "Milliseconds"},
            confidence=1.0,
        ),
        ActionDescriptor(
            id="act-global-navigate",
            op="navigate",
            label="Navigate to URL",
            enabled=True,
            requires_value=True,
            value_schema={"type": "string", "description": "URL"},
            navigational=True,
            confidence=1.0,
        ),
    ]
    for i, node in enumerate(nodes):
        fp = fingerprint_for(node)
        action = _action_for_node(node, id_map[fp], i)
        if action is not None:
            actions.append(action)

    regions = build_regions(nodes)
    forms = build_forms(nodes, actions)
    groups = build_content_groups(nodes)
    blockers = detect_blockers(nodes)
    confidence, warnings = confidence_from_nodes(nodes, len(actions), config.extraction)

    dom_stats = await capture_dom_stats(page)
    summary = PageSummary(
        headline=f"{page_info.page_type} page with {len(actions)} actions",
        key_points=[
            f"{len(regions)} regions",
            f"{len(forms)} forms",
            f"{len(groups)} content groups",
            f"{dom_stats.get('links', 0)} links",
        ],
    )
    extraction_ms = int((time.perf_counter() - start) * 1000)
    obs = Observation(
        session_id=session_id,
        mode=mode,  # type: ignore[arg-type]
        page=page_info,
        summary=summary,
        blockers=blockers,
        warnings=warnings,
        regions=regions,
        forms=forms,
        content_groups=groups,
        available_actions=actions,
        metrics=ObservationMetrics(
            extraction_ms=extraction_ms,
            action_count=len(actions),
            interactable_count=len(nodes),
            region_count=len(regions),
            form_count=len(forms),
            content_group_count=len(groups),
        ),
        confidence=confidence,
    )
    delta = build_delta(previous_observation, obs)
    payload_size = len(json.dumps(obs.model_dump(), default=str))
    delta_size = len(json.dumps(delta.model_dump(), default=str))
    obs.metrics.full_bytes = payload_size
    obs.metrics.delta_bytes = delta_size
    if mode == "delta":
        obs.summary = PageSummary(headline="Delta observation", key_points=delta.notes)
    return obs, id_map
