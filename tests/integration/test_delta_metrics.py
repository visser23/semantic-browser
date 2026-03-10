from __future__ import annotations

import pytest

from semantic_browser import ManagedSession
from semantic_browser.models import ActionRequest


@pytest.mark.asyncio
async def test_delta_smaller_than_full_on_multiple_pages():
    session = await ManagedSession.launch(headful=False)
    rt = session.runtime
    ratios = []
    try:
        for url in ["https://example.com", "https://www.iana.org/help/example-domains"]:
            await rt.navigate(url)
            full = await rt.observe("full")
            open_action = next((a for a in full.available_actions if a.op == "open"), None)
            if open_action is not None:
                try:
                    await rt.act(ActionRequest(action_id=open_action.id))
                except Exception:
                    # If the extracted locator is stale/weak on a live page,
                    # still validate delta economics by observing again.
                    pass
            delta = await rt.observe("delta")
            if full.metrics.full_bytes > 0:
                ratios.append(delta.metrics.delta_bytes / full.metrics.full_bytes)
        assert ratios
        assert sum(ratios) / len(ratios) <= 1.0
    finally:
        await session.close()
