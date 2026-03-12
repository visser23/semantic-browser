from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from semantic_browser.service.state import SessionHandle, SessionRegistry


class _Runtime:
    session_id = "sid"

    async def close(self):
        return None


@pytest.mark.asyncio
async def test_registry_cleanup_expires_idle_sessions():
    registry = SessionRegistry(session_ttl_seconds=60)
    runtime = _Runtime()
    sid = registry.add_runtime(runtime)
    handle = registry.get(sid)
    assert handle is not None

    assert isinstance(handle, SessionHandle)
    handle.last_accessed_at = datetime.now(tz=UTC) - timedelta(seconds=120)

    expired = await registry.cleanup_expired()
    assert sid in expired
    assert registry.get(sid) is None
