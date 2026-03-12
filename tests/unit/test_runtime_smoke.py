from __future__ import annotations

import json
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

    async def evaluate(self, script, *_args, **_kwargs):
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
    async def evaluate(self, script, *_args, **_kwargs):
        text = str(script)
        if "node_count" in text:
            self.node_snapshot_calls += 1
            if self.node_snapshot_calls < 3:
                return {"title": "Transient", "node_count": 0, "nodes": []}
        return await super().evaluate(script)


class DensePage(FakePage):
    async def evaluate(self, script, *_args, **_kwargs):
        text = str(script)
        if "node_count" in text:
            top_nodes = [
                {"tag": "a", "role": "link", "name": f"Top {i}", "type": "", "href": f"https://example.com/{i}", "disabled": False, "in_viewport": i < 4, "rect": {"x": 0, "y": i * 120, "w": 200, "h": 40}, "text": "Top"}
                for i in range(8)
            ]
            lower_nodes = [
                {"tag": "a", "role": "link", "name": f"Lower {i}", "type": "", "href": f"https://example.com/l{i}", "disabled": False, "in_viewport": False, "rect": {"x": 0, "y": 2400 + i * 120, "w": 200, "h": 40}, "text": "Lower"}
                for i in range(8)
            ]
            nodes = top_nodes + lower_nodes
            return {"title": "Dense", "node_count": len(nodes), "nodes": nodes}
        if text.strip() == "() => window.innerHeight || 1080":
            return 1000
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
    assert page.reload_calls == 0


@pytest.mark.asyncio
async def test_summary_mode_uses_top_scope_and_full_mode_includes_more_actions():
    runtime = SemanticBrowserRuntime.from_page(DensePage())
    summary_obs = await runtime.observe("summary")
    full_obs = await runtime.observe("full")
    assert len(full_obs.available_actions) > len(summary_obs.available_actions)
    assert any("top-scope" in point or "elements" in point for point in summary_obs.summary.key_points)


@pytest.mark.asyncio
async def test_auto_mode_sets_route_and_quality_metrics():
    runtime = SemanticBrowserRuntime.from_page(DensePage())
    obs = await runtime.observe("auto")
    assert obs.metrics.extraction_route is not None
    assert obs.metrics.aria_quality is not None
    assert obs.metrics.total_interactable_count is not None
    assert obs.metrics.scoped_interactable_count is not None


@pytest.mark.asyncio
async def test_planner_view_is_present_and_compact():
    runtime = SemanticBrowserRuntime.from_page(DensePage())
    obs = await runtime.observe("auto")
    assert obs.planner is not None
    assert obs.planner.location
    assert len(obs.planner.available_actions) <= 20
    assert obs.planner.room_text
    assert "@ " in obs.planner.room_text
    assert "> " in obs.planner.room_text
    planner_tokens = len(obs.planner.room_text)
    full_tokens = len(json.dumps(obs.model_dump(), default=str))
    assert planner_tokens < full_tokens


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
