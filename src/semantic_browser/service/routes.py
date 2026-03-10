"""HTTP routes for local service mode."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from semantic_browser.runtime import SemanticBrowserRuntime
from semantic_browser.service.schemas import (
    ActRequest,
    AttachRequest,
    InspectRequest,
    LaunchRequest,
    NavigateRequest,
    ObserveRequest,
)
from semantic_browser.service.state import SessionRegistry
from semantic_browser.session import ManagedSession

router = APIRouter()
_registry = SessionRegistry()


@router.post("/sessions/launch")
async def launch_session(req: LaunchRequest):
    session = await ManagedSession.launch(headful=req.headful)
    sid = _registry.add_managed(session)
    return {"session_id": sid, "mode": "managed"}


@router.post("/sessions/attach")
async def attach_session(req: AttachRequest):
    runtime = await SemanticBrowserRuntime.from_cdp_endpoint(req.cdp_endpoint)
    sid = _registry.add_runtime(runtime)
    return {"session_id": sid}


@router.post("/sessions/{session_id}/close")
async def close_session(session_id: str):
    handle = _registry.pop(session_id)
    if not handle:
        raise HTTPException(status_code=404, detail="session not found")
    await handle.close()
    return {"ok": True}


@router.post("/sessions/{session_id}/observe")
async def observe(session_id: str, req: ObserveRequest):
    runtime = _get_runtime(session_id)
    observation = await runtime.observe(mode=req.mode)
    return observation.model_dump(mode="json")


@router.post("/sessions/{session_id}/inspect")
async def inspect(session_id: str, req: InspectRequest):
    runtime = _get_runtime(session_id)
    return await runtime.inspect(req.target_id)


@router.post("/sessions/{session_id}/navigate")
async def navigate(session_id: str, req: NavigateRequest):
    runtime = _get_runtime(session_id)
    result = await runtime.navigate(req.url)
    return result.model_dump(mode="json")


@router.post("/sessions/{session_id}/act")
async def act(session_id: str, req: ActRequest):
    runtime = _get_runtime(session_id)
    result = await runtime.act(req.action)
    return result.model_dump(mode="json")


@router.post("/sessions/{session_id}/back")
async def back(session_id: str):
    runtime = _get_runtime(session_id)
    result = await runtime.back()
    return result.model_dump(mode="json")


@router.post("/sessions/{session_id}/forward")
async def forward(session_id: str):
    runtime = _get_runtime(session_id)
    result = await runtime.forward()
    return result.model_dump(mode="json")


@router.post("/sessions/{session_id}/reload")
async def reload(session_id: str):
    runtime = _get_runtime(session_id)
    result = await runtime.reload()
    return result.model_dump(mode="json")


@router.get("/sessions/{session_id}/diagnostics")
async def diagnostics(session_id: str):
    runtime = _get_runtime(session_id)
    return (await runtime.diagnostics()).model_dump(mode="json")


@router.post("/sessions/{session_id}/export-trace")
async def export_trace(session_id: str):
    runtime = _get_runtime(session_id)
    path = await runtime.export_trace(f"trace-{session_id}.json")
    return {"path": path}


def _get_runtime(session_id: str):
    handle = _registry.get(session_id)
    if not handle:
        raise HTTPException(status_code=404, detail="session not found")
    return handle.runtime
