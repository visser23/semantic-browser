"""HTTP route schemas."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from semantic_browser.models import ActionRequest


class LaunchRequest(BaseModel):
    headful: bool = True
    profile_mode: Literal["persistent", "clone", "ephemeral"] = "ephemeral"
    profile_dir: str | None = None
    storage_state_path: str | None = None


class AttachRequest(BaseModel):
    cdp_endpoint: str


class ObserveRequest(BaseModel):
    mode: str = "summary"


class InspectRequest(BaseModel):
    target_id: str


class NavigateRequest(BaseModel):
    url: str


class ActRequest(BaseModel):
    action: ActionRequest


class ExportTraceRequest(BaseModel):
    out_path: str | None = None
