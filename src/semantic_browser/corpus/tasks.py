"""Corpus task execution."""

from __future__ import annotations

import asyncio
from typing import Any

from semantic_browser import ManagedSession


async def run_site_task(entry: dict[str, Any], *, headful: bool) -> dict[str, Any]:
    session = await ManagedSession.launch(headful=headful)
    runtime = session.runtime
    try:
        await asyncio.wait_for(runtime.navigate(str(entry["url"])), timeout=25)
        obs = await asyncio.wait_for(runtime.observe(mode="summary"), timeout=25)
        return {
            "site": entry.get("site"),
            "url": entry.get("url"),
            "page_type": obs.page.page_type,
            "action_count": len(obs.available_actions),
            "region_count": len(obs.regions),
            "form_count": len(obs.forms),
            "confidence": obs.confidence.overall,
        }
    except Exception as exc:
        return {
            "site": entry.get("site"),
            "url": entry.get("url"),
            "page_type": "error",
            "action_count": 0,
            "region_count": 0,
            "form_count": 0,
            "confidence": 0.0,
            "error": str(exc),
        }
    finally:
        await session.close()
