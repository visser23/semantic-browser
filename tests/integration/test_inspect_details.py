from __future__ import annotations

import pytest

from semantic_browser import ManagedSession


@pytest.mark.asyncio
async def test_inspect_region_form_or_group():
    session = await ManagedSession.launch(headful=False)
    rt = session.runtime
    try:
        await rt.navigate("https://example.com")
        obs = await rt.observe("summary")
        candidate = None
        if obs.forms:
            candidate = obs.forms[0].id
        elif obs.content_groups:
            candidate = obs.content_groups[0].id
        elif obs.regions:
            candidate = obs.regions[0].id
        if candidate is None:
            pytest.skip("No inspectable target in observation")
        detail = await rt.inspect(candidate)
        assert detail["kind"] in {"form", "content_group", "region"}
    finally:
        await session.close()
