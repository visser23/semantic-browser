from __future__ import annotations

import pytest

from semantic_browser.runtime import SemanticBrowserRuntime


class _Page:
    url = "https://example.com"


class _CDPManager:
    def __init__(self) -> None:
        self.stopped = False
        self.closed = False

    async def stop(self):
        self.stopped = True

    async def close(self):
        self.closed = True


@pytest.mark.asyncio
async def test_close_in_attached_context_mode_is_non_destructive():
    runtime = SemanticBrowserRuntime(
        page=_Page(),
        managed=False,
        attached_kind="context",
        ownership_mode="attached_context",
    )
    await runtime.close()


@pytest.mark.asyncio
async def test_close_in_attached_cdp_stops_playwright_not_browser():
    manager = {"pw": _CDPManager(), "browser": _CDPManager()}
    runtime = SemanticBrowserRuntime(
        page=_Page(),
        managed=False,
        manager=manager,
        attached_kind="cdp",
        ownership_mode="attached_cdp",
    )
    await runtime.close()
    assert manager["pw"].stopped is True
    assert manager["browser"].closed is False


@pytest.mark.asyncio
async def test_force_close_browser_closes_in_attached_mode():
    manager = {"pw": _CDPManager(), "browser": _CDPManager()}
    runtime = SemanticBrowserRuntime(
        page=_Page(),
        managed=False,
        manager=manager,
        attached_kind="cdp",
        ownership_mode="attached_cdp",
    )
    await runtime.force_close_browser()
    assert manager["pw"].stopped is True
    assert manager["browser"].closed is True
