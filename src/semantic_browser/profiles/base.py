"""Profile base types."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class SiteProfile:
    name: str
    domains: list[str]

    def applies(self, domain: str) -> bool:
        return any(domain.endswith(d) for d in self.domains)
