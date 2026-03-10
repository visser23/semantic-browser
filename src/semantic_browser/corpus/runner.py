"""Corpus runner entrypoint."""

from __future__ import annotations

from typing import Any

from semantic_browser.corpus.fixtures import load_sites_config
from semantic_browser.corpus.metrics import aggregate_report, score_site_result
from semantic_browser.corpus.tasks import run_site_task


async def run_corpus(*, config_path: str, headful: bool) -> dict[str, Any]:
    entries = load_sites_config(config_path)
    scored: list[dict[str, Any]] = []
    for entry in entries:
        result = await run_site_task(entry, headful=headful)
        scored.append(score_site_result(entry, result))
    return aggregate_report(scored)
