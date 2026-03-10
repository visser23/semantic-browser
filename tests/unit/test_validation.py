import pytest

from semantic_browser.errors import ActionNotFoundError, ActionStaleError
from semantic_browser.executor.validation import resolve_action
from semantic_browser.models import ActionDescriptor, ActionRequest, Observation, PageInfo, PageSummary


def _obs() -> Observation:
    return Observation(
        session_id="s1",
        mode="summary",
        page=PageInfo(
            url="https://example.com",
            title="Example",
            domain="example.com",
            page_type="generic",
            page_identity="example.com:example",
            ready_state="complete",
            modal_active=False,
            frame_count=1,
        ),
        summary=PageSummary(headline="h"),
        available_actions=[
            ActionDescriptor(id="a-open", op="open", label="Open", target_id="elm-1", confidence=0.9),
            ActionDescriptor(id="a-wait", op="wait", label="Wait", confidence=1.0),
        ],
    )


def test_resolve_by_action_id():
    action = resolve_action(ActionRequest(action_id="a-open"), _obs())
    assert action.op == "open"


def test_resolve_by_op_only():
    action = resolve_action(ActionRequest(op="wait"), _obs())
    assert action.id == "a-wait"


def test_resolve_stale_target_raises():
    with pytest.raises(ActionStaleError):
        resolve_action(ActionRequest(op="open", target_id="missing"), _obs())


def test_resolve_missing_action_raises():
    with pytest.raises(ActionNotFoundError):
        resolve_action(ActionRequest(action_id="missing"), _obs())
