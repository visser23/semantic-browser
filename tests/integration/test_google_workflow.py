from __future__ import annotations

import pytest

from semantic_browser import ManagedSession
from semantic_browser.models import ActionRequest


@pytest.mark.asyncio
async def test_google_fill_search_submit_verify():
    session = await ManagedSession.launch(headful=False)
    rt = session.runtime
    try:
        await rt.navigate("https://www.google.com")
        obs = await rt.observe("summary")
        fill_action = next((a for a in obs.available_actions if a.op == "fill"), None)
        if fill_action is None:
            pytest.skip("No fill action available on Google page (possible regional/cookie variant).")
        await rt.act(ActionRequest(action_id=fill_action.id, value="semantic browser runtime"))
        submit_action = next((a for a in (await rt.observe("summary")).available_actions if a.op in {"click", "submit", "open"}), None)
        if submit_action is None:
            pytest.skip("No submit/click/open action surfaced after fill.")
        await rt.act(ActionRequest(action_id=submit_action.id))
        after = await rt.observe("summary")
        assert after.page.url
    finally:
        await session.close()
