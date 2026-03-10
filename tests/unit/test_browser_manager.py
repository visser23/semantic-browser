from __future__ import annotations

import pytest

from semantic_browser.browser_manager import BrowserArtifacts, BrowserManager
from semantic_browser.errors import BrowserNotReadyError


class _Dummy:
    async def close(self):
        return None


class _PW:
    async def stop(self):
        return None


def test_artifacts_property_raises_before_launch():
    manager = BrowserManager(headful=False)
    with pytest.raises(BrowserNotReadyError):
        _ = manager.artifacts


@pytest.mark.asyncio
async def test_close_noop_without_launch():
    manager = BrowserManager(headful=False)
    await manager.close()


@pytest.mark.asyncio
async def test_close_cleans_artifacts():
    manager = BrowserManager(headful=False)
    manager._artifacts = BrowserArtifacts(playwright=_PW(), browser=_Dummy(), context=_Dummy(), page=object())  # type: ignore[attr-defined]
    await manager.close()
    assert manager._artifacts is None  # type: ignore[attr-defined]
