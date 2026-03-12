from semantic_browser.executor.results import build_execution, classify_status
from semantic_browser.models import Blocker, Observation, ObservationDelta, PageInfo, PageSummary


def test_classify_success_when_changes():
    status = classify_status(True, "clicked", ObservationDelta(changed_values={"x": 1}))
    assert status == "success"


def test_classify_blocked_when_blocker_added():
    delta = ObservationDelta(
        added_blockers=[Blocker(kind="modal", severity="medium", description="Modal detected")]
    )
    assert classify_status(True, "ok", delta) == "blocked"


def test_classify_wait_as_success():
    assert classify_status(True, "waited", ObservationDelta()) == "success"


def _obs(url: str) -> Observation:
    return Observation(
        session_id="s1",
        mode="summary",
        page=PageInfo(
            url=url,
            title="title",
            domain="example.com",
            page_type="generic",
            page_identity="id",
            ready_state="complete",
            modal_active=False,
            frame_count=1,
        ),
        summary=PageSummary(headline="h"),
    )


def test_build_execution_sets_effect_from_delta():
    before = _obs("https://a.example.com")
    after = _obs("https://b.example.com")
    delta = ObservationDelta(navigated=True)
    execution = build_execution("open", True, "clicked", before, after, delta)
    assert execution.effect == "navigation"
