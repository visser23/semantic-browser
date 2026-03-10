from __future__ import annotations

import pytest

from semantic_browser.errors import AttachmentError
from semantic_browser.runtime import SemanticBrowserRuntime


@pytest.mark.asyncio
async def test_from_cdp_endpoint_rejects_page_websocket_endpoint():
    with pytest.raises(AttachmentError, match="browser websocket endpoint"):
        await SemanticBrowserRuntime.from_cdp_endpoint(
            "ws://127.0.0.1:18800/devtools/page/abc123"
        )
