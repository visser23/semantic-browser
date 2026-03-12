"""Profile registry lookup."""

from __future__ import annotations

from semantic_browser.profiles.base import SiteProfile
from semantic_browser.profiles.generic import GENERIC_PROFILE


class ProfileRegistry:
    def __init__(self, profiles: list[SiteProfile] | None = None) -> None:
        self._profiles = profiles or []

    def for_domain(self, domain: str) -> SiteProfile:
        for p in self._profiles:
            if p.applies(domain):
                return p
        return GENERIC_PROFILE
