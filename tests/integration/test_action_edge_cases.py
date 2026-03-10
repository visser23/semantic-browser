from __future__ import annotations

import urllib.parse

import pytest

from semantic_browser import ManagedSession
from semantic_browser.models import ActionRequest


@pytest.mark.asyncio
async def test_act_on_stale_element_returns_non_success():
    html_a = "<html><body><a href='https://example.com'>Go</a></body></html>"
    html_b = "<html><body><p>No links now</p></body></html>"
    url_a = "data:text/html," + urllib.parse.quote(html_a)
    url_b = "data:text/html," + urllib.parse.quote(html_b)

    session = await ManagedSession.launch(headful=False)
    rt = session.runtime
    try:
        await rt.navigate(url_a)
        obs = await rt.observe("summary")
        open_action = next((a for a in obs.available_actions if a.op == "open"), None)
        if open_action is None:
            pytest.skip("No open action found in fixture page.")
        await rt.navigate(url_b)
        result = await rt.act(ActionRequest(action_id=open_action.id))
        assert result.status in {"stale", "failed", "ambiguous", "invalid", "blocked"}
    finally:
        await session.close()


@pytest.mark.asyncio
async def test_act_on_disabled_element_returns_non_success():
    html = "<html><body><button disabled>Disabled</button></body></html>"
    url = "data:text/html," + urllib.parse.quote(html)
    session = await ManagedSession.launch(headful=False)
    rt = session.runtime
    try:
        await rt.navigate(url)
        obs = await rt.observe("summary")
        click_action = next((a for a in obs.available_actions if a.op == "click"), None)
        if click_action is None:
            pytest.skip("No click action surfaced for disabled fixture.")
        result = await rt.act(ActionRequest(action_id=click_action.id))
        assert result.status in {"failed", "blocked", "ambiguous", "stale", "invalid"}
    finally:
        await session.close()
