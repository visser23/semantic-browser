"""Corpus fixture loading."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


def load_sites_config(path: str) -> list[dict[str, Any]]:
    cfg_path = Path(path)
    if not cfg_path.exists():
        raise FileNotFoundError(f"Corpus config not found: {path}")
    data = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("Corpus config must be a list of site entries.")
    return [d for d in data if isinstance(d, dict)]
