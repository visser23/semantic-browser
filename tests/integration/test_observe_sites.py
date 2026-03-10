from __future__ import annotations

import pytest

from semantic_browser import ManagedSession


@pytest.mark.asyncio
async def test_observe_example_structure():
    session = await ManagedSession.launch(headful=False)
    try:
        await session.runtime.navigate("https://example.com")
        obs = await session.runtime.observe("summary")
        assert obs.page.domain.endswith("example.com")
        assert len(obs.available_actions) >= 1
    finally:
        await session.close()


@pytest.mark.asyncio
async def test_observe_google_actions():
    session = await ManagedSession.launch(headful=False)
    try:
        await session.runtime.navigate("https://www.google.com")
        obs = await session.runtime.observe("summary")
        assert len(obs.available_actions) >= 1
    finally:
        await session.close()
