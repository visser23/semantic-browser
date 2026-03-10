from __future__ import annotations

import pytest

from semantic_browser.executor.resolver import resolve_locator
from semantic_browser.models import ActionDescriptor


class _DummyLocator:
    @property
    def first(self):
        return self


class _Page:
    def __init__(self):
        self.calls: list[tuple[str, tuple, dict]] = []

    def get_by_role(self, role, name=None):
        self.calls.append(("get_by_role", (role,), {"name": name}))
        return _DummyLocator()

    def get_by_label(self, name):
        self.calls.append(("get_by_label", (name,), {}))
        return _DummyLocator()

    def get_by_text(self, name):
        self.calls.append(("get_by_text", (name,), {}))
        return _DummyLocator()

    def locator(self, sel):
        self.calls.append(("locator", (sel,), {}))
        return _DummyLocator()


@pytest.mark.asyncio
async def test_resolver_prefers_role_then_name():
    page = _Page()
    action = ActionDescriptor(
        id="a1",
        op="click",
        label="Submit",
        confidence=0.9,
        locator_recipe={"role": "button", "name": "Submit", "tag": "button"},
    )
    await resolve_locator(page, action)
    assert page.calls[0][0] == "get_by_role"
