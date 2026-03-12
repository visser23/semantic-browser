from click.testing import CliRunner

from semantic_browser.cli import commands as commands_mod
from semantic_browser.cli.main import main
from semantic_browser.models import (
    ActionRequest,
    ExecutionResult,
    Observation,
    ObservationDelta,
    PageInfo,
    PageSummary,
    StepResult,
)


class _FakeRuntime:
    def __init__(self):
        self.session_id = "cli-session"
        self._obs = Observation(
            session_id=self.session_id,
            mode="summary",
            page=PageInfo(
                url="https://example.com",
                title="Example",
                domain="example.com",
                page_type="page",
                page_identity="example.com:example",
                ready_state="complete",
                modal_active=False,
                frame_count=1,
            ),
            summary=PageSummary(headline="ok"),
        )

    async def observe(self, mode="summary", **_kwargs):
        self._obs.mode = mode
        return self._obs

    async def navigate(self, url: str):
        self._obs.page.url = url
        return StepResult(
            request=ActionRequest(op="navigate", value=url),
            status="success",
            execution=ExecutionResult(op="navigate", ok=True),
            observation=self._obs,
            delta=ObservationDelta(),
        )

    async def act(self, req: ActionRequest):
        return StepResult(
            request=req,
            status="success",
            execution=ExecutionResult(op=req.op or "click", ok=True),
            observation=self._obs,
            delta=ObservationDelta(),
        )


class _FakeSession:
    def __init__(self):
        self.runtime = _FakeRuntime()

    async def close(self):
        return None


def test_cli_version_command():
    runner = CliRunner()
    result = runner.invoke(main, ["version"])
    assert result.exit_code == 0
    assert "semantic-browser" in result.output


def test_cli_doctor_command():
    runner = CliRunner()
    result = runner.invoke(main, ["doctor"])
    assert result.exit_code == 0
    assert "python" in result.output


def test_cli_launch_observe_act_flow(monkeypatch):
    async def fake_launch(**_kwargs):
        return _FakeSession()

    from semantic_browser import session as session_mod

    monkeypatch.setattr(session_mod.ManagedSession, "launch", fake_launch)
    commands_mod._sessions.clear()
    commands_mod._attached_runtimes.clear()

    runner = CliRunner()
    launch = runner.invoke(main, ["launch", "--headless", "--json-output"])
    assert launch.exit_code == 0
    assert "session_id" in launch.output
    session_id = "cli-session"

    observed = runner.invoke(main, ["observe", "--session", session_id, "--mode", "summary", "--json-output"])
    assert observed.exit_code == 0
    assert "available_actions" in observed.output

    acted = runner.invoke(main, ["act", "--session", session_id, "--action", "wait", "--value", "100", "--json-output"])
    assert acted.exit_code == 0
    assert '"status": "success"' in acted.output


def test_cli_returns_error_for_unknown_session():
    commands_mod._sessions.clear()
    commands_mod._attached_runtimes.clear()
    runner = CliRunner()
    observed = runner.invoke(main, ["observe", "--session", "missing", "--mode", "summary"])
    assert observed.exit_code != 0
    assert "Unknown session" in observed.output
