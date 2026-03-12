from __future__ import annotations

from datetime import UTC, datetime

from fastapi.testclient import TestClient

from semantic_browser.models import (
    ActionRequest,
    DiagnosticsReport,
    ExecutionResult,
    Observation,
    ObservationDelta,
    PageInfo,
    PageSummary,
    StepResult,
)
from semantic_browser.service import routes as routes_mod
from semantic_browser.service.server import create_app
from semantic_browser.service.settings import ServiceSettings
from semantic_browser.service.state import SessionRegistry


class FakeRuntime:
    def __init__(self):
        self.session_id = "fake-session"
        self._obs = Observation(
            session_id="fake-session",
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
            summary=PageSummary(headline="ok"),
        )

    async def observe(self, mode="summary"):
        self._obs.mode = mode
        return self._obs

    async def inspect(self, _target_id: str):
        return {"kind": "unknown"}

    async def act(self, req: ActionRequest):
        return StepResult(
            request=req,
            status="success",
            execution=ExecutionResult(op=req.op or "click", ok=True),
            observation=self._obs,
            delta=ObservationDelta(),
        )

    async def navigate(self, _url: str):
        return StepResult(
            request=ActionRequest(op="navigate"),
            status="success",
            execution=ExecutionResult(op="navigate", ok=True),
            observation=self._obs,
            delta=ObservationDelta(),
        )

    async def back(self):
        return await self.navigate("back")

    async def forward(self):
        return await self.navigate("forward")

    async def reload(self):
        return await self.navigate("reload")

    async def diagnostics(self):
        return DiagnosticsReport(
            session_id=self.session_id,
            managed=False,
            attached_kind="page",
            current_url="https://example.com",
            last_observation_at=datetime.now(tz=UTC),
        )

    async def export_trace(self, _path: str):
        return "trace.json"

    async def close(self):
        return None


class FakeSession:
    def __init__(self):
        self.runtime = FakeRuntime()

    async def close(self):
        return None


def test_service_launch_observe_act_close(monkeypatch):
    captured: dict[str, object] = {}

    async def fake_launch(**_kwargs):
        captured.update(_kwargs)
        return FakeSession()

    from semantic_browser import session as session_mod

    monkeypatch.setattr(session_mod.ManagedSession, "launch", fake_launch)

    app = create_app()
    client = TestClient(app)
    launched = client.post("/sessions/launch", json={"headful": False})
    assert launched.status_code == 200
    assert captured.get("profile_mode") == "ephemeral"
    sid = launched.json()["session_id"]

    observed = client.post(f"/sessions/{sid}/observe", json={"mode": "summary"})
    assert observed.status_code == 200
    assert observed.json()["session_id"] == sid

    acted = client.post(
        f"/sessions/{sid}/act",
        json={"action": {"op": "wait", "value": 100}},
    )
    assert acted.status_code == 200
    assert acted.json()["status"] == "success"

    closed = client.post(f"/sessions/{sid}/close")
    assert closed.status_code == 200


def test_service_launch_supports_profile_payload(monkeypatch):
    captured: dict[str, object] = {}

    async def fake_launch(**kwargs):
        captured.update(kwargs)
        return FakeSession()

    from semantic_browser import session as session_mod

    monkeypatch.setattr(session_mod.ManagedSession, "launch", fake_launch)
    app = create_app()
    client = TestClient(app)
    launched = client.post(
        "/sessions/launch",
        json={
            "headful": False,
            "profile_mode": "persistent",
            "profile_dir": "/tmp/profile",
            "storage_state_path": None,
        },
    )
    assert launched.status_code == 200
    assert captured["profile_mode"] == "persistent"
    assert captured["profile_dir"] == "/tmp/profile"


def test_service_requires_token_when_configured(monkeypatch):
    async def fake_launch(**_kwargs):
        return FakeSession()

    from semantic_browser import session as session_mod

    monkeypatch.setattr(session_mod.ManagedSession, "launch", fake_launch)
    monkeypatch.setattr(
        routes_mod,
        "_settings",
        ServiceSettings(
            api_token="dev-token",
            allow_origins=["http://127.0.0.1", "http://localhost"],
            session_ttl_seconds=1800,
        ),
    )
    monkeypatch.setattr(routes_mod, "_registry", SessionRegistry(session_ttl_seconds=1800))

    app = create_app()
    client = TestClient(app)
    unauthorized = client.post("/sessions/launch", json={"headful": False})
    assert unauthorized.status_code == 401

    authorized = client.post(
        "/sessions/launch",
        json={"headful": False},
        headers={"X-API-Token": "dev-token"},
    )
    assert authorized.status_code == 200
