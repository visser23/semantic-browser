from __future__ import annotations

import urllib.parse

import pytest

from semantic_browser import ManagedSession


@pytest.mark.asyncio
async def test_cookie_banner_blocker_detected():
    html = """
    <html><body>
      <div role="dialog">Cookie consent <button>Accept all cookies</button></div>
      <main><a href="https://example.com">link</a></main>
    </body></html>
    """
    url = "data:text/html," + urllib.parse.quote(html)
    session = await ManagedSession.launch(headful=False)
    try:
        await session.runtime.navigate(url)
        obs = await session.runtime.observe("summary")
        assert any(b.kind == "cookie_banner" for b in obs.blockers)
    finally:
        await session.close()


@pytest.mark.asyncio
async def test_semantically_poor_page_low_confidence():
    html = "<html><body>" + "".join("<button></button>" for _ in range(60)) + "</body></html>"
    url = "data:text/html," + urllib.parse.quote(html)
    session = await ManagedSession.launch(headful=False)
    try:
        await session.runtime.navigate(url)
        obs = await session.runtime.observe("summary")
        assert obs.confidence.overall < 0.8 or any(w.kind == "low_semantic_quality" for w in obs.warnings)
    finally:
        await session.close()
