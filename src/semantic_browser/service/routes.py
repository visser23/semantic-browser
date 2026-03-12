"""HTTP routes for local service mode."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, status

from semantic_browser.runtime import SemanticBrowserRuntime
from semantic_browser.service.schemas import (
    ActRequest,
    AttachRequest,
    ExportTraceRequest,
    InspectRequest,
    LaunchRequest,
    NavigateRequest,
    ObserveRequest,
)
from semantic_browser.service.settings import load_service_settings
from semantic_browser.service.state import SessionRegistry
from semantic_browser.session import ManagedSession

router = APIRouter()
_settings = load_service_settings()
_registry = SessionRegistry(session_ttl_seconds=_settings.session_ttl_seconds)


async def shutdown_registry() -> None:
    await _registry.close_all()


def _require_token(x_api_token: str | None = Header(default=None, alias="X-API-Token")) -> None:
    if _settings.auth_enabled and x_api_token != _settings.api_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="unauthorized")


@router.post("/sessions/launch")
async def launch_session(req: LaunchRequest, _: None = Depends(_require_token)):
    await _registry.cleanup_expired()
    session = await ManagedSession.launch(
        headful=req.headful,
        profile_mode=req.profile_mode,
        profile_dir=req.profile_dir,
        storage_state_path=req.storage_state_path,
    )
    sid = _registry.add_managed(session)
    return {"session_id": sid, "mode": "managed"}


@router.post("/sessions/attach")
async def attach_session(req: AttachRequest, _: None = Depends(_require_token)):
    await _registry.cleanup_expired()
    runtime = await SemanticBrowserRuntime.from_cdp_endpoint(req.cdp_endpoint)
    sid = _registry.add_runtime(runtime)
    return {"session_id": sid}


@router.post("/sessions/{session_id}/close")
async def close_session(session_id: str, _: None = Depends(_require_token)):
    handle = _registry.pop(session_id)
    if not handle:
        raise HTTPException(status_code=404, detail="session not found")
    await handle.close()
    return {"ok": True}


@router.post("/sessions/{session_id}/observe")
async def observe(session_id: str, req: ObserveRequest, _: None = Depends(_require_token)):
    runtime = _get_runtime(session_id)
    observation = await runtime.observe(mode=req.mode)
    return observation.model_dump(mode="json")


@router.post("/sessions/{session_id}/inspect")
async def inspect(session_id: str, req: InspectRequest, _: None = Depends(_require_token)):
    runtime = _get_runtime(session_id)
    return await runtime.inspect(req.target_id)


@router.post("/sessions/{session_id}/navigate")
async def navigate(session_id: str, req: NavigateRequest, _: None = Depends(_require_token)):
    runtime = _get_runtime(session_id)
    result = await runtime.navigate(req.url)
    return result.model_dump(mode="json")


@router.post("/sessions/{session_id}/act")
async def act(session_id: str, req: ActRequest, _: None = Depends(_require_token)):
    runtime = _get_runtime(session_id)
    result = await runtime.act(req.action)
    return result.model_dump(mode="json")


@router.post("/sessions/{session_id}/back")
async def back(session_id: str, _: None = Depends(_require_token)):
    runtime = _get_runtime(session_id)
    result = await runtime.back()
    return result.model_dump(mode="json")


@router.post("/sessions/{session_id}/forward")
async def forward(session_id: str, _: None = Depends(_require_token)):
    runtime = _get_runtime(session_id)
    result = await runtime.forward()
    return result.model_dump(mode="json")


@router.post("/sessions/{session_id}/reload")
async def reload(session_id: str, _: None = Depends(_require_token)):
    runtime = _get_runtime(session_id)
    result = await runtime.reload()
    return result.model_dump(mode="json")


@router.get("/sessions/{session_id}/diagnostics")
async def diagnostics(session_id: str, _: None = Depends(_require_token)):
    runtime = _get_runtime(session_id)
    return (await runtime.diagnostics()).model_dump(mode="json")


@router.post("/sessions/{session_id}/export-trace")
async def export_trace(
    session_id: str,
    req: ExportTraceRequest,
    _: None = Depends(_require_token),
):
    runtime = _get_runtime(session_id)
    path = await runtime.export_trace(req.out_path or f"trace-{session_id}.json")
    return {"path": path}


def _get_runtime(session_id: str):
    handle = _registry.get(session_id)
    if not handle:
        raise HTTPException(status_code=404, detail="session not found")
    return handle.runtime
