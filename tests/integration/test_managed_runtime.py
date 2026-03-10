from __future__ import annotations

import pytest

from semantic_browser import ManagedSession, SemanticBrowserRuntime


@pytest.mark.asyncio
async def test_managed_launch_navigate_close():
    session = await ManagedSession.launch(headful=False)
    try:
        result = await session.runtime.navigate("https://example.com")
        assert result.status == "success"
        obs = await session.runtime.observe("summary")
        assert obs.page.domain.endswith("example.com")
    finally:
        await session.close()


@pytest.mark.asyncio
async def test_attached_from_page_navigate_detach():
    session = await ManagedSession.launch(headful=False)
    artifacts = session._manager.artifacts  # type: ignore[attr-defined]
    runtime = SemanticBrowserRuntime.from_page(artifacts.page)
    try:
        result = await runtime.navigate("https://example.com")
        assert result.status == "success"
    finally:
        await runtime.close()
        await session.close()
