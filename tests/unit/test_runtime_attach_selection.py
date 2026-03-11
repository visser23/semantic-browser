from __future__ import annotations

import types

import pytest

from semantic_browser.errors import AttachmentError
from semantic_browser.runtime import SemanticBrowserRuntime


class StubPage:
    def __init__(self, url: str):
        self.url = url


def test_select_page_prefers_non_blank_by_default():
    pages = [StubPage("about:blank"), StubPage("https://x.com/home")]
    picked = SemanticBrowserRuntime._select_page(pages)
    assert picked.url == "https://x.com/home"


def test_select_page_can_match_url_fragment():
    pages = [StubPage("https://example.com"), StubPage("https://x.com/explore")]
    picked = SemanticBrowserRuntime._select_page(pages, target_url_contains="x.com")
    assert picked.url == "https://x.com/explore"


def test_select_page_can_pick_by_index():
    pages = [StubPage("https://a.com"), StubPage("https://b.com")]
    picked = SemanticBrowserRuntime._select_page(pages, page_index=1)
    assert picked.url == "https://b.com"


def test_from_context_raises_when_no_pages():
    context = types.SimpleNamespace(pages=[])
    with pytest.raises(AttachmentError):
        SemanticBrowserRuntime.from_context(context)
