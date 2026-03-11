from __future__ import annotations

import sys
import types

import pytest

from semantic_browser.errors import AttachmentError
from semantic_browser.runtime import SemanticBrowserRuntime


class _FakeContext:
    def __init__(self, pages):
        self.pages = pages

    async def new_page(self):
        page = types.SimpleNamespace(url="about:blank")
        self.pages.append(page)
        return page


class _FakeBrowser:
    def __init__(self, pages):
        self.contexts = [_FakeContext(pages)]


class _FakePlaywright:
    def __init__(self, pages):
        self.chromium = types.SimpleNamespace(connect_over_cdp=self._connect)
        self._pages = pages

    async def _connect(self, endpoint: str):
        del endpoint
        return _FakeBrowser(self._pages)

    async def stop(self):
        return None


def _install_fake_playwright(monkeypatch, pages):
    async def _start():
        return _FakePlaywright(pages)

    def _factory():
        return types.SimpleNamespace(start=_start)

    monkeypatch.setitem(sys.modules, "playwright.async_api", types.SimpleNamespace(async_playwright=_factory))


@pytest.mark.asyncio
async def test_from_cdp_endpoint_rejects_page_websocket_endpoint():
    with pytest.raises(AttachmentError, match="browser websocket endpoint"):
        await SemanticBrowserRuntime.from_cdp_endpoint(
            "ws://127.0.0.1:18800/devtools/page/abc123"
        )


@pytest.mark.asyncio
async def test_from_cdp_endpoint_rejects_negative_page_index():
    with pytest.raises(AttachmentError, match="page_index must be >= 0"):
        await SemanticBrowserRuntime.from_cdp_endpoint(
            "ws://127.0.0.1:18800/devtools/browser/abc123",
            page_index=-1,
        )


@pytest.mark.asyncio
async def test_from_cdp_endpoint_rejects_page_index_out_of_range(monkeypatch):
    _install_fake_playwright(monkeypatch, pages=[types.SimpleNamespace(url="https://x.com/home")])

    with pytest.raises(AttachmentError, match="out of range"):
        await SemanticBrowserRuntime.from_cdp_endpoint(
            "ws://127.0.0.1:18800/devtools/browser/abc123",
            page_index=2,
        )


@pytest.mark.asyncio
async def test_from_cdp_endpoint_rejects_page_index_when_no_pages(monkeypatch):
    _install_fake_playwright(monkeypatch, pages=[])

    with pytest.raises(AttachmentError, match="no pages are open"):
        await SemanticBrowserRuntime.from_cdp_endpoint(
            "ws://127.0.0.1:18800/devtools/browser/abc123",
            page_index=0,
        )
