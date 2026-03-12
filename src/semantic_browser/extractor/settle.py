"""Composite settle strategy."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, cast

from semantic_browser.config import SettleConfig
from semantic_browser.errors import SettleTimeoutError


@dataclass
class SettleReport:
    durations_ms: dict[str, int] = field(default_factory=dict)
    instability: list[str] = field(default_factory=list)


def _as_int(value: object, default: int = 0) -> int:
    try:
        return int(cast(Any, value))
    except Exception:
        return default


async def wait_for_settle(page: Any, config: SettleConfig, *, intent: str = "action") -> SettleReport:
    max_settle_ms = int(getattr(config, "max_settle_ms", 15000))
    settle_profile_fast_ms = int(getattr(config, "settle_profile_fast_ms", 1500))
    settle_profile_slow_ms = int(getattr(config, "settle_profile_slow_ms", 4000))
    nav_stable_hits = int(getattr(config, "nav_stable_hits", 2))
    structural_stable_hits = int(getattr(config, "structural_stable_hits", 2))
    behavioral_stable_hits = int(getattr(config, "behavioral_stable_hits", 2))
    frame_stable_hits = int(getattr(config, "frame_stable_hits", 2))
    interactable_stable_ms = int(getattr(config, "interactable_stable_ms", 200))
    mutation_quiet_ms = int(getattr(config, "mutation_quiet_ms", 300))
    ready_states = list(getattr(config, "ready_states", ["interactive", "complete"]))
    deadline = time.monotonic() + (max_settle_ms / 1000)
    report = SettleReport()
    # Keep simple fast-path for low-risk intents.
    if intent in {"fill", "observe"}:
        local_deadline = min(deadline, time.monotonic() + (settle_profile_fast_ms / 1000))
    else:
        local_deadline = min(deadline, time.monotonic() + (settle_profile_slow_ms / 1000))

    nav_start = time.perf_counter()
    nav_hits = 0
    while time.monotonic() < local_deadline:
        try:
            state = await page.evaluate("document.readyState")
        except Exception:
            await asyncio.sleep(0.05)
            continue
        if state in ready_states:
            nav_hits += 1
            if nav_hits >= nav_stable_hits:
                break
        else:
            nav_hits = 0
        await asyncio.sleep(0.05)
    report.durations_ms["navigation_settle"] = int((time.perf_counter() - nav_start) * 1000)

    previous_signature: tuple[int, int] | None = None
    structural_hits = 0
    structural_start = time.perf_counter()
    resets = 0
    while time.monotonic() < deadline:
        try:
            signature = await page.evaluate(
                """
                () => {
                  const sel = 'a[href],button,input,select,textarea,[role="button"]';
                  const regionSel = 'main,nav,header,footer,aside,section,article,[role="dialog"],[role="form"]';
                  const all = Array.from(document.querySelectorAll(sel));
                  const interactables = all.filter(el => {
                    const s = window.getComputedStyle(el);
                    const rect = el.getBoundingClientRect();
                    return s.display !== 'none' && s.visibility !== 'hidden' && rect.width > 0 && rect.height > 0;
                  }).length;
                  const regions = document.querySelectorAll(regionSel).length;
                  return [interactables, regions];
                }
                """
            )
        except Exception:
            await asyncio.sleep(0.05)
            continue
        if not isinstance(signature, (list, tuple)) or len(signature) < 2:
            sig_struct = (_as_int(signature, 0), 0)
        else:
            sig_struct = (_as_int(signature[0], 0), _as_int(signature[1], 0))
        if previous_signature is None or previous_signature == sig_struct:
            structural_hits += 1
        else:
            resets += 1
            structural_hits = 0
        previous_signature = sig_struct
        if structural_hits >= structural_stable_hits:
            break
        await asyncio.sleep(interactable_stable_ms / 1000)
    report.durations_ms["structural_settle"] = int((time.perf_counter() - structural_start) * 1000)

    previous_behavioral: tuple[int, int, str] | None = None
    behavioral_hits = 0
    behavioral_start = time.perf_counter()
    while time.monotonic() < deadline:
        try:
            state = await page.evaluate(
                """
                () => {
                  const dialogs = document.querySelectorAll('[role="dialog"],[aria-modal="true"],dialog[open]').length;
                  const suggestions = document.querySelectorAll('[role="listbox"],[role="menu"],[aria-expanded="true"]').length;
                  const active = document.activeElement;
                  const activeSig = active ? `${active.tagName}:${active.getAttribute('role') || ''}:${active.id || ''}` : '';
                  return [dialogs, suggestions, activeSig];
                }
                """
            )
        except Exception:
            await asyncio.sleep(0.05)
            continue
        if not isinstance(state, (list, tuple)) or len(state) < 3:
            sig_behavioral = (0, 0, "")
        else:
            sig_behavioral = (_as_int(state[0], 0), _as_int(state[1], 0), str(state[2]))
        if previous_behavioral is None or previous_behavioral == sig_behavioral:
            behavioral_hits += 1
        else:
            behavioral_hits = 0
        previous_behavioral = sig_behavioral
        if behavioral_hits >= behavioral_stable_hits:
            break
        await asyncio.sleep(0.1)
    report.durations_ms["behavioral_settle"] = int((time.perf_counter() - behavioral_start) * 1000)

    previous_frame: tuple[int, int] | None = None
    frame_hits = 0
    frame_start = time.perf_counter()
    while time.monotonic() < deadline:
        try:
            frame_state = await page.evaluate(
                """
                () => {
                  const frames = document.querySelectorAll('iframe').length;
                  const frameInteractables = Array.from(document.querySelectorAll('iframe')).filter(f => {
                    const rect = f.getBoundingClientRect();
                    return rect.width > 0 && rect.height > 0;
                  }).length;
                  return [frames, frameInteractables];
                }
                """
            )
        except Exception:
            await asyncio.sleep(0.05)
            continue
        if not isinstance(frame_state, (list, tuple)) or len(frame_state) < 2:
            sig_frame = (0, 0)
        else:
            sig_frame = (_as_int(frame_state[0], 0), _as_int(frame_state[1], 0))
        if previous_frame is None or previous_frame == sig_frame:
            frame_hits += 1
        else:
            frame_hits = 0
        previous_frame = sig_frame
        if frame_hits >= frame_stable_hits:
            break
        await asyncio.sleep(0.1)
    report.durations_ms["frame_settle"] = int((time.perf_counter() - frame_start) * 1000)

    if resets >= 4:
        report.instability.append("mutation_storm")
    if previous_behavioral and previous_behavioral[0] > 0:
        report.instability.append("overlay_interference")
    if report.durations_ms["navigation_settle"] > settle_profile_slow_ms:
        report.instability.append("delayed_hydration")
    if not previous_signature or previous_signature[0] == 0:
        report.instability.append("unreachable_target")

    if time.monotonic() >= deadline:
        raise SettleTimeoutError("Page did not settle before timeout.")

    await asyncio.sleep(mutation_quiet_ms / 1000)
    return report
