from __future__ import annotations

import types

import pytest

from semantic_browser.extractor.ax_snapshot import capture_ax_snapshot
from semantic_browser.extractor.classifier import classify_page
from semantic_browser.extractor.dom_snapshot import capture_dom_stats
from semantic_browser.extractor.labels import normalized_label
from semantic_browser.extractor.page_state import capture_page_info
from semantic_browser.extractor.semantics import extract_semantics
from semantic_browser.extractor.settle import wait_for_settle
from semantic_browser.extractor.visibility import in_viewport


class FakePage:
    def __init__(self):
        self.url = "https://example.com"
        self.frames = [object()]
        self.accessibility = types.SimpleNamespace(snapshot=self._ax)

    async def _ax(self):
        return {"role": "WebArea", "name": "Example"}

    async def title(self):
        return "Example Domain"

    async def evaluate(self, script):
        text = str(script)
        if "document.readyState" in text:
            return "complete"
        if "querySelectorAll(sel)" in text:
            return 1
        if "querySelector('[role=\"dialog\"" in text:
            return False
        if "html_length" in text:
            return {"html_length": 100, "forms": 0, "links": 1, "inputs": 0}
        if "node_count" in text:
            return {
                "title": "Example Domain",
                "node_count": 2,
                "nodes": [
                    {"tag": "main", "role": "main", "name": "Main", "type": "", "href": "", "disabled": False, "in_viewport": True, "text": "content"},
                    {"tag": "a", "role": "link", "name": "More", "type": "", "href": "https://example.com/more", "disabled": False, "in_viewport": True, "text": "more"},
                ],
            }
        return "generic"


@pytest.mark.asyncio
async def test_extractors_smoke():
    page = FakePage()
    await wait_for_settle(page, types.SimpleNamespace(ready_states=["complete"], mutation_quiet_ms=1, interactable_stable_ms=1, max_settle_ms=2000))
    info = await capture_page_info(page)
    sem = await extract_semantics(page)
    dom = await capture_dom_stats(page)
    ax = await capture_ax_snapshot(page)
    assert info.domain == "example.com"
    assert sem["node_count"] >= 1
    assert dom["links"] >= 1
    assert ax["role"] == "WebArea"
    assert classify_page(sem["nodes"]) in {"generic", "navigation-heavy", "form", "article", "table", "login"}
    assert normalized_label("  hello   world ") == "hello world"
    assert in_viewport({"in_viewport": True}) is True
