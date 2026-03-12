"""Managed browser lifecycle support."""

from __future__ import annotations

import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from semantic_browser.errors import BrowserNotReadyError


@dataclass
class BrowserArtifacts:
    playwright: Any
    browser: Any | None
    context: Any
    page: Any


class BrowserManager:
    """Owns Playwright objects for managed mode."""

    def __init__(
        self,
        headful: bool = True,
        profile_mode: str = "ephemeral",
        profile_dir: str | None = None,
        storage_state_path: str | None = None,
    ) -> None:
        self._headful = headful
        self._profile_mode = profile_mode
        self._profile_dir = profile_dir
        self._storage_state_path = storage_state_path
        self._artifacts: BrowserArtifacts | None = None
        self._runtime_profile_dir: str | None = None
        self._profile_warnings: list[str] = []

    @property
    def profile_warnings(self) -> list[str]:
        return list(self._profile_warnings)

    @property
    def artifacts(self) -> BrowserArtifacts:
        if self._artifacts is None:
            raise BrowserNotReadyError("Managed browser has not been launched.")
        return self._artifacts

    async def launch(self, browser_path: str | None = None) -> BrowserArtifacts:
        try:
            from playwright.async_api import async_playwright
        except Exception as exc:
            raise BrowserNotReadyError(
                "Playwright is not installed. Install semantic-browser[managed]."
            ) from exc

        pw = await async_playwright().start()
        launch_kwargs: dict[str, Any] = {"headless": not self._headful}
        if browser_path:
            launch_kwargs["executable_path"] = browser_path
        browser = None
        if self._profile_mode == "persistent":
            profile_dir = self._require_profile_dir()
            self._profile_warnings.extend(self._check_profile_health(profile_dir))
            context = await pw.chromium.launch_persistent_context(user_data_dir=profile_dir, **launch_kwargs)
            page = context.pages[0] if context.pages else await context.new_page()
        elif self._profile_mode == "clone":
            source_dir = self._require_profile_dir()
            self._profile_warnings.extend(self._check_profile_health(source_dir))
            clone_dir = tempfile.mkdtemp(prefix="semantic-browser-profile-")
            shutil.copytree(source_dir, clone_dir, dirs_exist_ok=True)
            self._runtime_profile_dir = clone_dir
            context = await pw.chromium.launch_persistent_context(user_data_dir=clone_dir, **launch_kwargs)
            page = context.pages[0] if context.pages else await context.new_page()
        elif self._profile_mode == "ephemeral":
            browser = await pw.chromium.launch(**launch_kwargs)
            context_kwargs: dict[str, Any] = {}
            if self._storage_state_path:
                context_kwargs["storage_state"] = self._storage_state_path
            context = await browser.new_context(**context_kwargs)
            page = await context.new_page()
        else:
            await pw.stop()
            raise BrowserNotReadyError(
                f"Unknown profile_mode '{self._profile_mode}'. Expected persistent, clone, or ephemeral."
            )
        self._artifacts = BrowserArtifacts(
            playwright=pw, browser=browser, context=context, page=page
        )
        return self._artifacts

    async def close(self) -> None:
        if self._artifacts is None:
            return
        try:
            await self._artifacts.context.close()
        finally:
            try:
                if self._artifacts.browser is not None:
                    await self._artifacts.browser.close()
            finally:
                await self._artifacts.playwright.stop()
        if self._runtime_profile_dir:
            shutil.rmtree(self._runtime_profile_dir, ignore_errors=True)
            self._runtime_profile_dir = None
        self._artifacts = None

    def _require_profile_dir(self) -> str:
        if not self._profile_dir:
            raise BrowserNotReadyError("profile_dir is required for profile_mode persistent or clone.")
        return self._profile_dir

    def _check_profile_health(self, profile_dir: str) -> list[str]:
        warnings: list[str] = []
        path = Path(profile_dir)
        if not path.exists():
            raise BrowserNotReadyError(f"profile_dir does not exist: {profile_dir}")
        if not path.is_dir():
            raise BrowserNotReadyError(f"profile_dir is not a directory: {profile_dir}")
        if not os.access(path, os.W_OK):
            warnings.append("profile path is not writable; some session updates may fail")
        if (path / "SingletonLock").exists():
            warnings.append("profile appears locked by another Chrome process")
        if (path / "Last Version").exists():
            warnings.append("profile version compatibility is browser-dependent; verify Chrome channel compatibility")
        return warnings
