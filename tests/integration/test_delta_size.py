from __future__ import annotations

import pytest

from semantic_browser import ManagedSession
from semantic_browser.models import ActionRequest


@pytest.mark.asyncio
async def test_delta_smaller_than_full_after_action():
    session = await ManagedSession.launch(headful=False)
    runtime = session.runtime
    try:
        await runtime.navigate("https://example.com")
        full = await runtime.observe("full")
        open_action = next((a for a in full.available_actions if a.op == "open"), None)
        if open_action is not None:
            await runtime.act(ActionRequest(action_id=open_action.id))
        delta = await runtime.observe("delta")
        assert delta.metrics.delta_bytes <= full.metrics.full_bytes
    finally:
        await session.close()
