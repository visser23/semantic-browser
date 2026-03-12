from __future__ import annotations

import pytest

from semantic_browser.executor import actions as actions_mod
from semantic_browser.models import ActionDescriptor, ActionRequest


class _Locator:
    async def click(self, timeout=5000):
        return None

    async def fill(self, _value: str, timeout=5000):
        return None

    async def press(self, _value: str):
        return None

    async def evaluate(self, _script: str):
        return "button"

    async def input_value(self):
        return ""

    async def type(self, _value: str, timeout=5000):
        return None


class _Page:
    def __init__(self):
        self.url = "https://example.com/a"
        self.context = type("Ctx", (), {"pages": [object()]})()
        self.keyboard = type("KB", (), {"press": self._press})()

    async def _press(self, _value: str):
        return None

    async def goto(self, url: str, **_kwargs):
        self.url = url
        return None

    async def go_back(self):
        return None

    async def go_forward(self):
        return None

    async def reload(self):
        return None

    async def wait_for_timeout(self, _ms: int):
        return None

    async def evaluate(self, _script: str):
        return 0


@pytest.mark.asyncio
async def test_open_reports_navigation_effect(monkeypatch):
    async def fake_locator(_page, _action):
        return _Locator()

    monkeypatch.setattr(actions_mod, "_locator", fake_locator)
    page = _Page()
    action = ActionDescriptor(id="a1", op="open", label="Open", locator_recipe={})
    result = await actions_mod.execute_action(page, action, ActionRequest(action_id="a1"))
    assert result.effect_hint == "navigation"


@pytest.mark.asyncio
async def test_submit_prefers_control_when_available(monkeypatch):
    async def fake_locator(_page, _action):
        return _Locator()

    monkeypatch.setattr(actions_mod, "_locator", fake_locator)
    page = _Page()
    action = ActionDescriptor(id="a2", op="submit", label="Submit", locator_recipe={})
    result = await actions_mod.execute_action(page, action, ActionRequest(action_id="a2"))
    assert result.evidence.get("submit_strategy") == "control"
