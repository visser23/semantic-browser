"""Managed session API."""

from __future__ import annotations

from semantic_browser.browser_manager import BrowserManager
from semantic_browser.config import RuntimeConfig
from semantic_browser.models import OwnershipMode
from semantic_browser.runtime import SemanticBrowserRuntime


class ManagedSession:
    """Managed browser lifecycle container."""

    def __init__(self, manager: BrowserManager, runtime: SemanticBrowserRuntime) -> None:
        self._manager = manager
        self._runtime = runtime

    @classmethod
    async def launch(
        cls,
        headful: bool = True,
        profile_mode: str = "ephemeral",
        profile_dir: str | None = None,
        storage_state_path: str | None = None,
        browser_path: str | None = None,
        config: RuntimeConfig | None = None,
    ):
        manager = BrowserManager(
            headful=headful,
            profile_mode=profile_mode,
            profile_dir=profile_dir,
            storage_state_path=storage_state_path,
        )
        artifacts = await manager.launch(browser_path=browser_path)
        ownership_mode: OwnershipMode = (
            "owned_persistent_profile" if profile_mode in {"persistent", "clone"} else "owned_ephemeral"
        )
        runtime = SemanticBrowserRuntime(
            page=artifacts.page,
            config=config,
            managed=True,
            manager=manager,
            attached_kind="managed",
            ownership_mode=ownership_mode,
            profile_warnings=manager.profile_warnings,
        )
        return cls(manager=manager, runtime=runtime)

    @property
    def runtime(self) -> SemanticBrowserRuntime:
        return self._runtime

    async def new_page(self):
        artifacts = self._manager.artifacts
        return await artifacts.context.new_page()

    async def close(self) -> None:
        await self._runtime.close()
