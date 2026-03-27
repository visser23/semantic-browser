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


@pytest.mark.asyncio
async def test_custom_element_uses_css_selector_first():
    """Custom web components should resolve via CSS selector, not ARIA."""
    page = _Page()
    action = ActionDescriptor(
        id="a2",
        op="click",
        label="7/10",
        confidence=0.75,
        locator_recipe={
            "role": "",
            "name": "7/10",
            "tag": "abc-button",
            "css_selector": "abc-button.btn-odds",
            "is_custom_element": True,
        },
    )
    loc = await resolve_locator(page, action)
    assert page.calls[0][0] == "locator"
    assert page.calls[0][1] == ("abc-button.btn-odds",)
    assert len(page.calls) == 1  # No ARIA fallback attempted


class _FailingPage(_Page):
    """Page that raises on all ARIA methods but supports locator()."""

    def get_by_role(self, role, name=None):
        self.calls.append(("get_by_role", (role,), {"name": name}))
        raise ValueError("not found")

    def get_by_label(self, name):
        self.calls.append(("get_by_label", (name,), {}))
        raise ValueError("not found")

    def get_by_text(self, name):
        self.calls.append(("get_by_text", (name,), {}))
        raise ValueError("not found")


@pytest.mark.asyncio
async def test_css_selector_fallback_when_aria_fails():
    """Standard elements with css_selector should fall back to it if all ARIA methods fail."""
    page = _FailingPage()
    action = ActionDescriptor(
        id="a3",
        op="click",
        label="Mystery Button",
        confidence=0.7,
        locator_recipe={
            "role": "",
            "name": "Mystery Button",
            "tag": "div",
            "css_selector": "div.special-button",
        },
    )
    loc = await resolve_locator(page, action)
    # ARIA methods are tried and fail, then css_selector fallback is used
    assert any(call[0] == "locator" and call[1] == ("div.special-button",) for call in page.calls)


@pytest.mark.asyncio
async def test_standard_html_button_still_uses_aria():
    """Standard HTML buttons must still resolve via ARIA (regression test)."""
    page = _Page()
    action = ActionDescriptor(
        id="a4",
        op="click",
        label="Submit",
        confidence=0.9,
        locator_recipe={
            "role": "button",
            "name": "Submit",
            "tag": "button",
            "css_selector": "button.submit-btn",
        },
    )
    await resolve_locator(page, action)
    # Should prefer ARIA over CSS selector for standard elements
    assert page.calls[0][0] == "get_by_role"


@pytest.mark.asyncio
async def test_fallback_to_body_when_no_recipe():
    page = _Page()
    action = ActionDescriptor(
        id="a5",
        op="click",
        label="",
        confidence=0.5,
        locator_recipe={},
    )
    loc = await resolve_locator(page, action)
    assert page.calls[-1][0] == "locator"
    assert page.calls[-1][1] == ("body",)


@pytest.mark.asyncio
async def test_dom_id_resolution():
    page = _Page()
    action = ActionDescriptor(
        id="a6",
        op="click",
        label="Click Me",
        confidence=0.8,
        locator_recipe={"dom_id": "my-button", "tag": "button", "name": "Click Me"},
    )
    # role is empty, so get_by_role is skipped; get_by_text tried then dom_id via locator
    await resolve_locator(page, action)
    assert any(call[0] == "locator" and call[1] == ("#my-button",) for call in page.calls)
