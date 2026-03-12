from __future__ import annotations

from pathlib import Path

import pytest

from semantic_browser.browser_manager import BrowserManager
from semantic_browser.errors import BrowserNotReadyError


def test_persistent_mode_requires_profile_dir():
    manager = BrowserManager(profile_mode="persistent")
    with pytest.raises(BrowserNotReadyError, match="profile_dir is required"):
        manager._require_profile_dir()  # type: ignore[attr-defined]


def test_profile_health_reports_lock_and_version_files(tmp_path: Path):
    profile_dir = tmp_path / "profile"
    profile_dir.mkdir()
    (profile_dir / "SingletonLock").write_text("", encoding="utf-8")
    (profile_dir / "Last Version").write_text("1", encoding="utf-8")
    manager = BrowserManager(profile_mode="persistent", profile_dir=str(profile_dir))
    warnings = manager._check_profile_health(str(profile_dir))  # type: ignore[attr-defined]
    assert any("locked" in w for w in warnings)
    assert any("compatibility" in w for w in warnings)
