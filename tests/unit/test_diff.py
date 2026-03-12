from semantic_browser.extractor.diff import build_delta
from semantic_browser.models import (
    ActionDescriptor,
    Observation,
    PageInfo,
    PageSummary,
)


def _obs(url: str, action_enabled: bool = True) -> Observation:
    return Observation(
        session_id="s1",
        mode="summary",
        page=PageInfo(
            url=url,
            title="t",
            domain="example.com",
            page_type="generic",
            page_identity=f"id:{url}",
            ready_state="complete",
            modal_active=False,
            frame_count=1,
        ),
        summary=PageSummary(headline="h"),
        available_actions=[
            ActionDescriptor(id="a1", op="click", label="Go", enabled=action_enabled, confidence=0.9)
        ],
    )


def test_delta_initial():
    current = _obs("https://example.com")
    delta = build_delta(None, current)
    assert delta.changed_values["initial_observation"] is True
    assert delta.materiality == "minor"


def test_delta_navigation():
    prev = _obs("https://a.example.com")
    curr = _obs("https://b.example.com")
    delta = build_delta(prev, curr)
    assert delta.navigated is True
    assert delta.materiality in {"moderate", "major"}


def test_delta_enabled_disabled():
    prev = _obs("https://example.com", action_enabled=True)
    curr = _obs("https://example.com", action_enabled=False)
    delta = build_delta(prev, curr)
    assert "a1" in delta.disabled_actions
