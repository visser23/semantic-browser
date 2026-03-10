"""In-memory service session registry."""

from __future__ import annotations

from dataclasses import dataclass

from semantic_browser.runtime import SemanticBrowserRuntime
from semantic_browser.session import ManagedSession


@dataclass
class SessionHandle:
    runtime: SemanticBrowserRuntime
    managed_session: ManagedSession | None = None

    async def close(self) -> None:
        if self.managed_session is not None:
            await self.managed_session.close()
            return
        await self.runtime.close()


class SessionRegistry:
    def __init__(self) -> None:
        self._items: dict[str, SessionHandle] = {}

    def get(self, session_id: str) -> SessionHandle | None:
        return self._items.get(session_id)

    def add_managed(self, session: ManagedSession) -> str:
        sid = session.runtime.session_id
        self._items[sid] = SessionHandle(runtime=session.runtime, managed_session=session)
        return sid

    def add_runtime(self, runtime: SemanticBrowserRuntime) -> str:
        sid = runtime.session_id
        self._items[sid] = SessionHandle(runtime=runtime)
        return sid

    def pop(self, session_id: str) -> SessionHandle | None:
        return self._items.pop(session_id, None)
