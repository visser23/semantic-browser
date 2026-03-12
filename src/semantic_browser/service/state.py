"""In-memory service session registry."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from semantic_browser.runtime import SemanticBrowserRuntime
from semantic_browser.session import ManagedSession


@dataclass
class SessionHandle:
    runtime: SemanticBrowserRuntime
    managed_session: ManagedSession | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(tz=UTC))
    last_accessed_at: datetime = field(default_factory=lambda: datetime.now(tz=UTC))

    async def close(self) -> None:
        if self.managed_session is not None:
            await self.managed_session.close()
            return
        await self.runtime.close()


class SessionRegistry:
    def __init__(self, *, session_ttl_seconds: int = 1800) -> None:
        self._items: dict[str, SessionHandle] = {}
        self._session_ttl_seconds = session_ttl_seconds
        self._expired_pending_close: dict[str, SessionHandle] = {}

    def _touch(self, handle: SessionHandle) -> None:
        handle.last_accessed_at = datetime.now(tz=UTC)

    def _is_expired(self, handle: SessionHandle) -> bool:
        age_seconds = (datetime.now(tz=UTC) - handle.last_accessed_at).total_seconds()
        return age_seconds > self._session_ttl_seconds

    async def cleanup_expired(self) -> list[str]:
        if self._expired_pending_close:
            pending = list(self._expired_pending_close.items())
            self._expired_pending_close.clear()
            for _sid, handle in pending:
                await handle.close()
        expired = [sid for sid, handle in self._items.items() if self._is_expired(handle)]
        for sid in expired:
            popped = self._items.pop(sid, None)
            if popped is not None:
                await popped.close()
        return expired

    def get(self, session_id: str) -> SessionHandle | None:
        handle = self._items.get(session_id)
        if handle is None:
            return None
        if self._is_expired(handle):
            popped = self._items.pop(session_id, None)
            if popped is not None:
                self._expired_pending_close[session_id] = popped
            return None
        self._touch(handle)
        return handle

    def add_managed(self, session: ManagedSession) -> str:
        sid = session.runtime.session_id
        now = datetime.now(tz=UTC)
        self._items[sid] = SessionHandle(
            runtime=session.runtime,
            managed_session=session,
            created_at=now,
            last_accessed_at=now,
        )
        return sid

    def add_runtime(self, runtime: SemanticBrowserRuntime) -> str:
        sid = runtime.session_id
        now = datetime.now(tz=UTC)
        self._items[sid] = SessionHandle(runtime=runtime, created_at=now, last_accessed_at=now)
        return sid

    def pop(self, session_id: str) -> SessionHandle | None:
        return self._items.pop(session_id, None)

    async def close_all(self) -> None:
        items = list(self._items.items())
        self._items.clear()
        for _sid, handle in items:
            await handle.close()
