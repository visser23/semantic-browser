from __future__ import annotations

import types

import pytest

from semantic_browser.models import ActionRequest
from semantic_browser.runtime import SemanticBrowserRuntime


class FakeLocator:
    async def click(self, timeout=0):
        return None

    async def fill(self, value, timeout=0):
        return None

    async def select_option(self, value, timeout=0):
        return None

    async def press(self, key):
        return None

    async def scroll_into_view_if_needed(self, timeout=0):
        return None

    @property
    def first(self):
        return self


class FakePage:
    def __init__(self):
        self.url = "https://example.com"
        self.frames = [object()]
        self.accessibility = types.SimpleNamespace(snapshot=self._ax)
        self.keyboard = types.SimpleNamespace(press=self._press)
        self.node_snapshot_calls = 0
        self.reload_calls = 0

    async def _press(self, key):
        return None

    async def _ax(self):
        return {}

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
        if "node_count" in text:
            self.node_snapshot_calls += 1
            return {
                "title": "Example Domain",
                "node_count": 2,
                "nodes": [
                    {"tag": "main", "role": "main", "name": "Main", "type": "", "href": "", "disabled": False, "in_viewport": True, "text": "Main content"},
                    {"tag": "a", "role": "a", "name": "More", "type": "", "href": "https://example.com/more", "disabled": False, "in_viewport": True, "text": "More"},
                ],
            }
        if "html_length" in text:
            return {"html_length": 1000, "forms": 0, "links": 1, "inputs": 0}
        return None

    async def goto(self, url):
        self.url = url

    async def go_back(self):
        return None

    async def go_forward(self):
        return None

    async def reload(self, wait_until=None):
        _ = wait_until
        self.reload_calls += 1
        return None

    def get_by_role(self, role, name=None):
        return FakeLocator()

    def get_by_label(self, name):
        return FakeLocator()

    def get_by_text(self, name):
        return FakeLocator()

    def locator(self, _selector):
        return FakeLocator()

    async def wait_for_timeout(self, _ms):
        return None


class FlakyNoVisibleNodesPage(FakePage):
    async def evaluate(self, script):
        text = str(script)
        if "node_count" in text:
            self.node_snapshot_calls += 1
            if self.node_snapshot_calls < 3:
                return {"title": "Transient", "node_count": 0, "nodes": []}
        return await super().evaluate(script)


@pytest.mark.asyncio
async def test_runtime_observe_and_navigate():
    runtime = SemanticBrowserRuntime.from_page(FakePage())
    obs = await runtime.observe("summary")
    assert obs.page.domain == "example.com"
    result = await runtime.navigate("https://example.com/next")
    assert result.status == "success"


@pytest.mark.asyncio
async def test_runtime_observe_retries_on_no_visible_nodes_state():
    page = FlakyNoVisibleNodesPage()
    runtime = SemanticBrowserRuntime.from_page(page)
    obs = await runtime.observe("summary")
    assert obs.page.domain == "example.com"
    assert len(obs.available_actions) > 0
    assert page.node_snapshot_calls >= 3
    assert page.reload_calls == 1


@pytest.mark.asyncio
async def test_runtime_act():
    runtime = SemanticBrowserRuntime.from_page(FakePage())
    obs = await runtime.observe("summary")
    action = next(a for a in obs.available_actions if a.op in {"open", "click"})
    result = await runtime.act(ActionRequest(action_id=action.id))
    assert result.status in {"success", "ambiguous", "blocked"}


@pytest.mark.asyncio
async def test_runtime_global_ops():
    runtime = SemanticBrowserRuntime.from_page(FakePage())
    await runtime.observe("summary")
    wait_result = await runtime.act(ActionRequest(op="wait", value=10))
    assert wait_result.status in {"success", "ambiguous"}
