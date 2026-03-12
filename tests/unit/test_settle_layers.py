from __future__ import annotations

import pytest

from semantic_browser.config import SettleConfig
from semantic_browser.extractor.settle import wait_for_settle


class _Page:
    def __init__(self):
        self.url = "https://example.com"
        self.context = type("Ctx", (), {"pages": [object()]})()

    async def evaluate(self, script: str):
        if script == "document.readyState":
            return "complete"
        if "regionSel" in script:
            return [10, 4]
        if "activeSig" in script:
            return [0, 0, "INPUT:textbox:q"]
        if "querySelectorAll('iframe')" in script:
            return [1, 1]
        return 0

    async def wait_for_timeout(self, _ms: int):
        return None


@pytest.mark.asyncio
async def test_wait_for_settle_returns_layer_durations():
    report = await wait_for_settle(_Page(), SettleConfig(max_settle_ms=1000), intent="observe")
    assert "navigation_settle" in report.durations_ms
    assert "structural_settle" in report.durations_ms
    assert "behavioral_settle" in report.durations_ms
    assert "frame_settle" in report.durations_ms
