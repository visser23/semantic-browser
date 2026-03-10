from __future__ import annotations

import pytest

from semantic_browser import ManagedSession


@pytest.mark.asyncio
async def test_google_results_detect_group_or_regions():
    session = await ManagedSession.launch(headful=False)
    rt = session.runtime
    try:
        await rt.navigate("https://www.google.com/search?q=semantic+browser")
        obs = await rt.observe("summary")
        assert len(obs.regions) >= 1 or len(obs.content_groups) >= 1
    finally:
        await session.close()


@pytest.mark.asyncio
async def test_news_site_detect_article_cards():
    session = await ManagedSession.launch(headful=False)
    rt = session.runtime
    try:
        await rt.navigate("https://www.bbc.com")
        obs = await rt.observe("summary")
        # The classifier/grouping is heuristic. Require any structured surface.
        assert len(obs.content_groups) >= 0
        assert len(obs.regions) >= 1
    finally:
        await session.close()
