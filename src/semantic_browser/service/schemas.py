"""HTTP route schemas."""

from __future__ import annotations

from pydantic import BaseModel

from semantic_browser.models import ActionRequest


class LaunchRequest(BaseModel):
    headful: bool = True


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
