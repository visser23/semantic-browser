"""Region, form, and content grouping."""

from __future__ import annotations

import hashlib
from collections import defaultdict
from typing import Any

from semantic_browser.models import (
    ActionDescriptor,
    ContentGroupSummary,
    ContentItemPreview,
    FormSummary,
    RegionSummary,
)


def _stable_id(prefix: str, seed: str) -> str:
    digest = hashlib.sha1(seed.encode("utf-8")).hexdigest()[:10]
    return f"{prefix}-{digest}"


def build_regions(nodes: list[dict[str, Any]]) -> list[RegionSummary]:
    region_like = {"main", "nav", "header", "footer", "aside", "section", "article", "dialog", "form"}
    regions: list[RegionSummary] = []
    order = 0
    for node in nodes:
        if node["tag"] in region_like or node["role"] in {"main", "navigation", "dialog", "form"}:
            frame_id = str(node.get("frame_id") or "main")
            seed = "|".join([frame_id, str(node.get("role") or node.get("tag") or ""), str(node.get("name") or "")[:80]])
            rid = _stable_id("rgn", seed)
            regions.append(
                RegionSummary(
                    id=rid,
                    kind=node["role"],
                    name=node["name"] or node["tag"],
                    frame_id=frame_id,
                    order=order,
                    visible=True,
                    in_viewport=node["in_viewport"],
                    interactable_count=0,
                    content_item_count=0,
                    primary_action_ids=[],
                    preview_text=(node["text"] or None),
                )
            )
            order += 1
    if not regions:
        regions.append(
            RegionSummary(
                id="rgn-root",
                kind="root",
                name="Document",
                frame_id="main",
                order=0,
                visible=True,
                in_viewport=True,
                interactable_count=0,
                content_item_count=0,
                primary_action_ids=[],
            )
        )
    return regions


def build_forms(nodes: list[dict[str, Any]], actions: list[ActionDescriptor]) -> list[FormSummary]:
    forms: list[FormSummary] = []
    form_nodes = [n for n in nodes if n["tag"] == "form" or n["role"] == "form"]
    for idx, node in enumerate(form_nodes):
        fields = [
            a.target_id
            for a in actions
            if a.op in {"fill", "select_option", "toggle"} and (a.target_id or "").startswith("elm-")
        ]
        submit_ids = [a.id for a in actions if a.op in {"submit", "click"} and "submit" in a.label.lower()]
        frame_id = str(node.get("frame_id") or "main")
        form_name = node["name"] or f"Form {idx+1}"
        form_id = _stable_id("frm", "|".join([frame_id, form_name[:80], str(idx)]))
        forms.append(
            FormSummary(
                id=form_id,
                name=form_name,
                frame_id=frame_id,
                field_ids=[f for f in fields if f],
                submit_action_ids=submit_ids,
                validity="unknown",
                required_missing=[],
            )
        )
    return forms


def build_content_groups(nodes: list[dict[str, Any]]) -> list[ContentGroupSummary]:
    buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for n in nodes:
        if n["tag"] in {"li", "article"} or n["role"] in {"listitem", "row"}:
            key = f"{n.get('frame_id') or 'main'}::{n['role'] or n['tag']}"
            buckets[key].append(n)
    groups: list[ContentGroupSummary] = []
    for idx, (bucket_key, items) in enumerate(buckets.items()):
        kind = bucket_key.split("::", 1)[1] if "::" in bucket_key else bucket_key
        group_id = _stable_id("grp", f"{bucket_key}|{len(items)}|{idx}")
        previews = [
            ContentItemPreview(
                id=_stable_id("itm", f"{group_id}|{i}|{item.get('name') or item.get('text') or ''}"),
                title=(item["name"] or item["text"][:80] or None),
                subtitle=item["text"][:120] or None,
            )
            for i, item in enumerate(items[:5])
        ]
        groups.append(
            ContentGroupSummary(
                id=group_id,
                kind=kind,
                name=f"{kind} items",
                item_count=len(items),
                visible_item_count=len(items),
                preview_items=previews,
            )
        )
    return groups
