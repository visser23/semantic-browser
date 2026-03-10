from semantic_browser.executor.results import classify_status
from semantic_browser.models import Blocker, ObservationDelta


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
