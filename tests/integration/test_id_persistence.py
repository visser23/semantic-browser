from __future__ import annotations

import pytest

from semantic_browser import ManagedSession


@pytest.mark.asyncio
async def test_ids_persist_on_reobserve_same_page():
    session = await ManagedSession.launch(headful=False)
    rt = session.runtime
    try:
        await rt.navigate("https://example.com")
        first = await rt.observe("summary")
        second = await rt.observe("summary")
        first_ids = {a.id for a in first.available_actions}
        second_ids = {a.id for a in second.available_actions}
        assert first_ids.intersection(second_ids)
    finally:
        await session.close()
