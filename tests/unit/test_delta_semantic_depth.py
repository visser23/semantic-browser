from __future__ import annotations

from semantic_browser.extractor.diff import build_delta
from semantic_browser.models import (
    ContentGroupSummary,
    FormSummary,
    Observation,
    PageInfo,
    PageSummary,
)


def _obs(*, validity: str, item_count: int, modal: bool, confidence: float) -> Observation:
    return Observation(
        session_id="s1",
        mode="summary",
        page=PageInfo(
            url="https://example.com",
            title="t",
            domain="example.com",
            page_type="form",
            page_identity="example",
            ready_state="complete",
            modal_active=modal,
            frame_count=1,
        ),
        summary=PageSummary(headline="h"),
        forms=[
            FormSummary(
                id="frm1",
                name="Checkout",
                frame_id="main",
                field_ids=["elm-1"],
                submit_action_ids=["act-submit"],
                validity=validity,
                required_missing=[],
            )
        ],
        content_groups=[
            ContentGroupSummary(
                id="grp1",
                kind="listitem",
                name="Results",
                item_count=item_count,
                visible_item_count=item_count,
            )
        ],
        confidence={"overall": confidence, "extraction": confidence, "grouping": confidence, "actionability": confidence, "stability": confidence, "reasons": []},
    )


def test_delta_detects_workflow_and_content_changes():
    prev = _obs(validity="invalid", item_count=3, modal=False, confidence=0.8)
    curr = _obs(validity="valid", item_count=8, modal=True, confidence=0.55)
    delta = build_delta(prev, curr)
    assert any(item.startswith("form_validity:") for item in delta.workflow_state_changes)
    assert any(item.startswith("group_count:") for item in delta.content_state_changes)
    assert any(item.startswith("confidence_drift:") for item in delta.reliability_state_changes)
    assert delta.materiality in {"moderate", "major"}
