"""Extraction orchestrator."""

from __future__ import annotations

import json
import time
from typing import Any

from semantic_browser.config import RuntimeConfig
from semantic_browser.models import (
    ActionDescriptor,
    Blocker,
    Observation,
    ObservationMetrics,
    PageInfo,
    PageSummary,
    PlannerAction,
    PlannerView,
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

_MAX_CURATED_ACTIONS = 15
_SEE_MORE_ID = "more"


async def _viewport_height(page: Any) -> float:
    try:
        value = await page.evaluate("() => window.innerHeight || 1080")
        return float(value or 1080)
    except Exception:
        return 1080.0


def _node_in_top_scope(node: dict[str, Any], cutoff_y: float) -> bool:
    if bool(node.get("in_viewport", False)):
        return True
    rect = node.get("rect") or {}
    y = rect.get("y")
    h = rect.get("h")
    if y is None:
        return False
    try:
        y_f = float(y)
        h_f = float(h or 0)
    except Exception:
        return False
    return (y_f + max(h_f, 1.0)) <= cutoff_y


def _aria_quality_score(nodes: list[dict[str, Any]]) -> float:
    if not nodes:
        return 0.0
    names = [(n.get("name") or "").strip() for n in nodes]
    labelled = sum(1 for n in names if len(n) >= 2)
    label_cov = labelled / len(nodes)
    interactive = [n for n in nodes if n.get("tag") in {"a", "button", "input", "select", "textarea"} or n.get("role") in {"link", "button", "textbox", "checkbox"}]
    interactive_ratio = len(interactive) / len(nodes)
    unique_labels = len(set(n.lower() for n in names if n))
    duplicate_penalty = 1.0 - (unique_labels / max(labelled, 1))
    score = (0.65 * label_cov) + (0.25 * min(interactive_ratio * 2.0, 1.0)) + (0.10 * (1.0 - duplicate_penalty))
    return round(max(0.0, min(1.0, score)), 3)


async def _nodes_for_mode(nodes: list[dict[str, Any]], page: Any, mode: str, config: RuntimeConfig) -> tuple[list[dict[str, Any]], bool, str, float]:
    quality = _aria_quality_score(nodes)
    resolved_mode = mode
    if mode == "auto":
        resolved_mode = "summary" if quality >= 0.55 else "full"

    if resolved_mode != "summary" or not config.extraction.summary_top_scope_enabled:
        route = "semantic_full" if resolved_mode == "full" else "semantic_raw"
        return nodes, False, route, quality
    viewport_h = await _viewport_height(page)
    cutoff_y = viewport_h * max(config.extraction.summary_top_scope_multiplier, 1.0)
    scoped = [n for n in nodes if _node_in_top_scope(n, cutoff_y)]
    if not scoped:
        return nodes, False, "semantic_top", quality
    route = "aria_compact" if mode == "auto" and quality >= 0.75 else "semantic_top"
    return scoped, len(scoped) < len(nodes), route, quality


# ---------------------------------------------------------------------------
# Content narration helpers
# ---------------------------------------------------------------------------

def _extract_headings(nodes: list[dict[str, Any]]) -> list[str]:
    """Pull visible h1-h3 text from nodes for narration."""
    headings: list[str] = []
    for n in nodes:
        tag = n.get("tag", "")
        if tag in {"h1", "h2", "h3"} or n.get("role") in {"heading"}:
            text = (n.get("name") or n.get("text") or "").strip()
            if text and len(text) > 2:
                headings.append(text[:80])
    return headings[:5]


def _extract_nav_labels(nodes: list[dict[str, Any]]) -> list[str]:
    """Pull short navigation link labels from nav regions."""
    labels: list[str] = []
    in_nav = False
    for n in nodes:
        if n.get("tag") == "nav" or n.get("role") == "navigation":
            in_nav = True
            continue
        if in_nav and n.get("tag") in {"a", "button"} or n.get("role") in {"link", "button"}:
            name = (n.get("name") or "").strip()
            if name and len(name) < 30 and name not in labels:
                labels.append(name)
        if in_nav and n.get("tag") in {"main", "footer", "aside", "section", "article"}:
            in_nav = False
    return labels[:10]


def _build_narration(
    page_info: PageInfo,
    nodes: list[dict[str, Any]],
    regions: list[Any],
    content_groups: list[Any],
    forms: list[Any],
) -> str:
    """Build a short prose description of what's visible on the page."""
    parts: list[str] = []

    headings = _extract_headings(nodes)
    nav_labels = _extract_nav_labels(nodes)

    region_kinds = [r.kind for r in regions if r.kind not in {"root", "form"}]
    has_nav = any(k in {"navigation", "nav"} for k in region_kinds)

    page_desc = page_info.title or page_info.domain
    if headings:
        parts.append(f"{page_desc}. Main content: \"{headings[0]}\".")
        for h in headings[1:3]:
            parts.append(f'Also: "{h}".')
    else:
        parts.append(f"{page_desc}.")

    if has_nav and nav_labels:
        parts.append(f"Navigation: {', '.join(nav_labels[:8])}.")
    elif nav_labels:
        parts.append(f"Links: {', '.join(nav_labels[:6])}.")

    for fg in forms[:2]:
        parts.append(f"Form: {fg.name}.")

    for cg in content_groups[:2]:
        count = cg.item_count or 0
        if count > 1:
            preview = ""
            if cg.preview_items:
                first_title = (cg.preview_items[0].title or "")[:50]
                if first_title:
                    preview = f' (e.g. "{first_title}")'
            parts.append(f"{count} {cg.kind} items{preview}.")

    input_nodes = [n for n in nodes if n.get("tag") in {"input", "textarea", "select"} and not n.get("disabled")]
    if input_nodes:
        input_names = [(n.get("name") or n.get("type") or "input").strip()[:30] for n in input_nodes[:3]]
        if len(input_nodes) == 1:
            parts.append(f"Input field: {input_names[0]}.")
        else:
            parts.append(f"Input fields: {', '.join(input_names)}.")

    narration = " ".join(parts)
    if len(narration) > 200:
        narration = narration[:197] + "..."
    return narration


_CURATED_ROOM_BUDGET = 1000
_EXPANDED_ROOM_BUDGET = 4000


def _cap_room_text(text: str, budget: int) -> str:
    """Truncate room text to stay within a character budget."""
    if len(text) <= budget:
        return text
    return text[:budget - 3] + "..."


# ---------------------------------------------------------------------------
# Action curation — rank and prune for the planner
# ---------------------------------------------------------------------------

def _curate_actions(
    actions: list[ActionDescriptor],
    blockers: list[Blocker],
    limit: int = _MAX_CURATED_ACTIONS,
) -> tuple[list[ActionDescriptor], bool]:
    """Rank and prune actions for the planner room description.

    Priority order:
    1. Blocker-dismissal actions (cookie banners, modal close)
    2. Form inputs (fill, select, toggle) — task-critical
    3. Primary/CTA actions
    4. In-viewport navigation and buttons
    5. Remaining enabled actions

    Returns (curated_list, has_more) where has_more indicates
    there are additional actions beyond the curated set.
    """
    blocker_action_ids = set()
    for b in blockers:
        blocker_action_ids.update(b.related_action_ids)

    enabled = [a for a in actions if a.enabled]

    tier_blocker: list[ActionDescriptor] = []
    tier_input: list[ActionDescriptor] = []
    tier_primary: list[ActionDescriptor] = []
    tier_normal: list[ActionDescriptor] = []
    tier_global: list[ActionDescriptor] = []

    for a in enabled:
        if a.id in blocker_action_ids:
            tier_blocker.append(a)
        elif a.op in {"fill", "select_option"}:
            tier_input.append(a)
        elif a.primary or a.op in {"submit", "click"}:
            tier_primary.append(a)
        elif a.id in {"back", "fwd", "reload", "wait", "nav"}:
            tier_global.append(a)
        else:
            tier_normal.append(a)

    ranked = tier_blocker + tier_input + tier_primary + tier_normal
    curated = ranked[:limit]

    global_keepers = [g for g in tier_global if g.op in {"back", "navigate"}]
    curated.extend(global_keepers)

    has_more = len(ranked) > limit
    return curated, has_more


# ---------------------------------------------------------------------------
# Room description — the text-adventure output
# ---------------------------------------------------------------------------

def _format_action_line(idx: int, action: ActionDescriptor) -> str:
    """Format one action as a terse room description line."""
    label = action.label[:40]
    if action.requires_value:
        return f'{idx} {action.op} {label} [{action.id}] *value'
    return f'{idx} {action.op} "{label}" [{action.id}]'


def _build_room_text(
    page_info: PageInfo,
    narration: str,
    curated_actions: list[ActionDescriptor],
    blockers: list[Blocker],
    has_more: bool,
    total_action_count: int,
) -> str:
    """Render the full text-adventure room description (terse format)."""
    lines: list[str] = []

    lines.append(f"@ {page_info.title or page_info.domain} ({page_info.domain})")
    lines.append(f"> {narration}")

    if blockers:
        for b in blockers[:3]:
            dismiss_hint = ""
            if b.related_action_ids:
                dismiss_hint = f" -> dismiss [{b.related_action_ids[0]}]"
            lines.append(f"! {b.description}{dismiss_hint}")

    for i, action in enumerate(curated_actions, 1):
        lines.append(_format_action_line(i, action))

    if has_more:
        hidden = total_action_count - len(curated_actions)
        lines.append(f"+ {hidden} more [{_SEE_MORE_ID}]")

    return _cap_room_text("\n".join(lines), _CURATED_ROOM_BUDGET)


def _build_expanded_room_text(
    page_info: PageInfo,
    narration: str,
    actions: list[ActionDescriptor],
    blockers: list[Blocker],
) -> str:
    """Render expanded room description showing ALL actions (terse format)."""
    lines: list[str] = []

    lines.append(f"@ {page_info.title or page_info.domain} ({page_info.domain})")
    lines.append(f"> {narration}")

    if blockers:
        for b in blockers[:3]:
            dismiss_hint = ""
            if b.related_action_ids:
                dismiss_hint = f" -> dismiss [{b.related_action_ids[0]}]"
            lines.append(f"! {b.description}{dismiss_hint}")

    enabled = [a for a in actions if a.enabled]
    lines.append(f"== ALL {len(enabled)} ACTIONS ==")
    for i, action in enumerate(enabled, 1):
        lines.append(_format_action_line(i, action))

    lines.append("COMPLETE list. No hidden actions.")
    lines.append("If your target is not listed, try nav with a direct URL, or go back.")

    return _cap_room_text("\n".join(lines), _EXPANDED_ROOM_BUDGET)


# ---------------------------------------------------------------------------
# PlannerView builder (replaces old _build_planner_view)
# ---------------------------------------------------------------------------

def _build_planner_view(
    page_info: PageInfo,
    narration: str,
    blockers: list[Blocker],
    actions: list[ActionDescriptor],
    expanded: bool = False,
) -> PlannerView:
    total = sum(1 for a in actions if a.enabled)
    curated, has_more = _curate_actions(actions, blockers)

    if expanded:
        room_text = _build_expanded_room_text(page_info, narration, actions, blockers)
    else:
        room_text = _build_room_text(page_info, narration, curated, blockers, has_more, total)

    action_items = [
        PlannerAction(id=a.id, label=a.label, op=a.op)
        for a in curated
    ]

    return PlannerView(
        location=f"{page_info.title or page_info.domain} ({page_info.domain})",
        what_you_see=[narration],
        available_actions=action_items,
        blockers=[b.description for b in blockers[:5]],
        room_text=room_text,
        has_more_actions=has_more,
        total_action_count=total,
    )


def _action_for_node(node: dict[str, Any], node_id: str, action_id: str, idx: int) -> ActionDescriptor | None:
    role = node.get("role", "")
    tag = node.get("tag", "")
    name = (node.get("name") or "").strip() or f"{tag}-{idx}"
    disabled = bool(node.get("disabled", False))
    op = None
    requires_value = False
    if tag in {"input", "textarea"} or role in {"textbox"}:
        input_type = node.get("type", "")
        if input_type in {"checkbox", "radio"} or role == "checkbox":
            op = "toggle"
        elif input_type in {"submit", "button", "reset", "image"}:
            op = "click"
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
    elif role in {"tab", "menuitem", "option", "treeitem"}:
        op = "click"
    elif not op and (str(node.get("tabindex", "")) == "0" or node.get("has_click_handler")):
        op = "click"
    if not op:
        return None
    recipe = {
        "name": name,
        "role": role,
        "tag": tag,
        "type": node.get("type", ""),
        "dom_id": node.get("id", ""),
        "href": node.get("href", ""),
    }
    # Include CSS selector for custom web components (e.g. <abc-button>)
    # that are not exposed to the accessibility tree.
    css_sel = (node.get("css_selector") or "").strip()
    if css_sel:
        recipe["css_selector"] = css_sel
    if node.get("is_custom_element"):
        recipe["is_custom_element"] = True
    return ActionDescriptor(
        id=action_id,
        op=op,
        label=name,
        target_id=node_id,
        enabled=not disabled,
        requires_value=requires_value,
        navigational=op in {"open"},
        confidence=0.75 if node.get("is_custom_element") else 0.85,
        locator_recipe=recipe,
    )


async def observe_page(
    *,
    session_id: str,
    page: Any,
    mode: str,
    config: RuntimeConfig,
    previous_observation: Observation | None,
    previous_ids: dict[str, str] | None,
    expanded: bool = False,
) -> tuple[Observation, dict[str, str]]:
    start = time.perf_counter()

    fast_path = mode in {"auto", "summary"} and not expanded
    sem = await extract_semantics(
        page,
        include_frames=config.extraction.include_frames,
        max_elements=config.extraction.max_elements,
    )
    all_nodes = redact_nodes(sem.get("nodes", []), config.redaction)
    nodes, top_scoped, extraction_route, aria_quality = await _nodes_for_mode(all_nodes, page, mode, config)
    id_map = assign_node_ids(nodes, previous=previous_ids)
    page_info = await capture_page_info(page)
    if isinstance(sem.get("frame_count"), int):
        page_info.frame_count = max(1, int(sem.get("frame_count", 1)))

    use_fast_path = fast_path and aria_quality >= 0.7
    if not use_fast_path:
        page_info.page_type = classify_page(nodes)
    else:
        page_info.page_type = "page"

    actions: list[ActionDescriptor] = [
        ActionDescriptor(
            id="back",
            op="back",
            label="Back",
            enabled=True,
            navigational=True,
            confidence=0.9,
        ),
        ActionDescriptor(
            id="fwd",
            op="forward",
            label="Forward",
            enabled=True,
            navigational=True,
            confidence=0.9,
        ),
        ActionDescriptor(
            id="reload",
            op="reload",
            label="Reload",
            enabled=True,
            navigational=True,
            confidence=0.9,
        ),
        ActionDescriptor(
            id="wait",
            op="wait",
            label="Wait",
            enabled=True,
            requires_value=True,
            value_schema={"type": "integer", "description": "Milliseconds"},
            confidence=1.0,
        ),
        ActionDescriptor(
            id="nav",
            op="navigate",
            label="Navigate to URL",
            enabled=True,
            requires_value=True,
            value_schema={"type": "string", "description": "URL"},
            navigational=True,
            confidence=1.0,
        ),
    ]
    seen_fingerprints: dict[str, int] = {}
    for i, node in enumerate(nodes):
        fp = fingerprint_for(node)
        ordinal = seen_fingerprints.get(fp, 0)
        seen_fingerprints[fp] = ordinal + 1
        node_key = f"{fp}#{ordinal}"
        node_id = id_map.get(node_key, f"elm-{fp[:8]}-{ordinal}")
        action_id = f"act-{node_id.replace('elm-', '')}"
        action = _action_for_node(node, node_id, action_id, i)
        if action is not None:
            actions.append(action)

    regions = build_regions(nodes)
    blockers = detect_blockers(nodes)

    if use_fast_path:
        forms = build_forms(nodes, actions)
        groups = []
    else:
        forms = build_forms(nodes, actions)
        groups = build_content_groups(nodes)
        await capture_dom_stats(page)

    confidence, warnings = confidence_from_nodes(nodes, len(actions), config.extraction)

    narration = _build_narration(page_info, nodes, regions, groups, forms)

    key_points = [narration]
    if top_scoped:
        key_points.append(f"showing {len(nodes)}/{len(all_nodes)} elements (top-scope view)")
    summary = PageSummary(
        headline=f"{page_info.title or page_info.domain}",
        key_points=key_points,
    )

    extraction_ms = int((time.perf_counter() - start) * 1000)
    if use_fast_path:
        extraction_route = "fast_aria"

    planner = _build_planner_view(page_info, narration, blockers, actions, expanded=expanded)
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
        planner=planner,
        metrics=ObservationMetrics(
            extraction_ms=extraction_ms,
            action_count=len(actions),
            interactable_count=len(nodes),
            region_count=len(regions),
            form_count=len(forms),
            content_group_count=len(groups),
            extraction_route=extraction_route,
            aria_quality=aria_quality,
            scoped_interactable_count=len(nodes),
            total_interactable_count=len(all_nodes),
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
