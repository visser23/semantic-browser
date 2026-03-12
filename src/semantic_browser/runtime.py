"""Primary runtime API."""

from __future__ import annotations

import json
import time
import uuid
import warnings
from typing import Any

from semantic_browser.config import RuntimeConfig
from semantic_browser.errors import (
    ActionExecutionError,
    ActionNotFoundError,
    ActionStaleError,
    AttachmentError,
    BrowserNotReadyError,
    SettleTimeoutError,
)
from semantic_browser.executor.actions import execute_action
from semantic_browser.executor.results import build_execution, classify_status
from semantic_browser.executor.validation import resolve_action
from semantic_browser.extractor.diff import build_delta
from semantic_browser.extractor.engine import _SEE_MORE_ID, observe_page
from semantic_browser.extractor.settle import wait_for_settle
from semantic_browser.models import (
    ActionRequest,
    DiagnosticsReport,
    Observation,
    OwnershipMode,
    StepResult,
)
from semantic_browser.telemetry.debug_dump import export_json_bundle
from semantic_browser.telemetry.trace import TraceStore


class SemanticBrowserRuntime:
    """Deterministic semantic runtime for a live page."""

    def __init__(
        self,
        *,
        page: Any,
        config: RuntimeConfig | None = None,
        managed: bool = False,
        manager: Any | None = None,
        attached_kind: str = "page",
        ownership_mode: OwnershipMode = "owned_ephemeral",
        profile_warnings: list[str] | None = None,
    ) -> None:
        self._page = page
        self._config = config or RuntimeConfig()
        self._managed = managed
        self._manager = manager
        self._attached_kind = attached_kind
        self._ownership_mode = ownership_mode
        self._session_id = str(uuid.uuid4())
        self._current_observation: Observation | None = None
        self._id_map: dict[str, str] = {}
        self._last_expanded: bool = False
        self._trace = TraceStore(max_events=self._config.telemetry.max_events)
        self._profile_warnings = profile_warnings or []
        self._url_history: list[str] = []

    @classmethod
    def from_page(cls, page: Any, config: RuntimeConfig | None = None, profile_registry=None):
        del profile_registry
        if page is None:
            raise AttachmentError("Cannot attach to null page.")
        return cls(
            page=page,
            config=config,
            managed=False,
            attached_kind="page",
            ownership_mode="attached_context",
        )

    @staticmethod
    def _select_page(
        pages: list[Any],
        *,
        target_url_contains: str | None = None,
        page_index: int | None = None,
        prefer_non_blank: bool = True,
    ) -> Any | None:
        if not pages:
            return None
        if page_index is not None and 0 <= page_index < len(pages):
            return pages[page_index]
        if target_url_contains:
            needle = target_url_contains.lower()
            by_url = next((p for p in pages if needle in (getattr(p, "url", "") or "").lower()), None)
            if by_url:
                return by_url
        if prefer_non_blank:
            non_blank = next((p for p in pages if (getattr(p, "url", "") or "") not in {"", "about:blank"}), None)
            if non_blank:
                return non_blank
        return pages[0]

    @classmethod
    def from_context(cls, context: Any, config: RuntimeConfig | None = None, profile_registry=None):
        del profile_registry
        page = cls._select_page(context.pages, prefer_non_blank=True)
        if page is None:
            raise AttachmentError("Cannot attach: context has no pages.")
        return cls(
            page=page,
            config=config,
            managed=False,
            attached_kind="context",
            ownership_mode="attached_context",
        )

    @classmethod
    async def from_cdp_endpoint(
        cls,
        endpoint: str,
        config: RuntimeConfig | None = None,
        profile_registry=None,
        *,
        target_url_contains: str | None = None,
        page_index: int | None = None,
        prefer_non_blank: bool = True,
    ):
        del profile_registry
        if "/devtools/page/" in endpoint:
            raise AttachmentError(
                "CDP attach expects a browser websocket endpoint (/devtools/browser/...), "
                "not a page websocket endpoint (/devtools/page/...)."
            )
        if page_index is not None and page_index < 0:
            raise AttachmentError(f"CDP attach page_index must be >= 0 (got {page_index}).")
        try:
            from playwright.async_api import async_playwright
        except Exception as exc:
            raise AttachmentError("Playwright is required for CDP attach.") from exc
        pw = await async_playwright().start()
        try:
            browser = await pw.chromium.connect_over_cdp(endpoint)
            contexts = list(browser.contexts)
            context = contexts[0] if contexts else await browser.new_context()
            if page_index is not None:
                page_count = len(context.pages)
                if page_count == 0:
                    raise AttachmentError(
                        "CDP attach cannot select page_index when no pages are open in the target context."
                    )
                if page_index >= page_count:
                    raise AttachmentError(
                        f"CDP attach page_index {page_index} is out of range for {page_count} page(s)."
                    )
            page = cls._select_page(
                context.pages,
                target_url_contains=target_url_contains,
                page_index=page_index,
                prefer_non_blank=prefer_non_blank,
            )
            if page is None:
                page = await context.new_page()
            return cls(
                page=page,
                config=config,
                managed=False,
                manager={"pw": pw, "browser": browser, "attached_cdp": True},
                attached_kind="cdp",
                ownership_mode="attached_cdp",
            )
        except Exception as exc:
            try:
                await pw.stop()
            finally:
                pass
            raise AttachmentError(f"Failed CDP attach at {endpoint}: {exc}") from exc

    @property
    def session_id(self) -> str:
        return self._session_id

    @property
    def ownership_mode(self) -> OwnershipMode:
        return self._ownership_mode

    @staticmethod
    def _is_no_visible_nodes_state(observation: Observation) -> bool:
        reasons = {r.lower() for r in observation.confidence.reasons}
        return "no visible nodes" in reasons or (
            len(observation.available_actions) == 0 and observation.confidence.overall <= 0.2
        )

    async def observe(self, mode: str = "summary", *, expanded: bool = False) -> Observation:
        max_attempts = 3 if mode == "summary" else 1
        observation: Observation | None = None
        id_map: dict[str, str] = {}
        settle_timed_out = False
        settle_ms = 0
        for attempt in range(1, max_attempts + 1):
            settle_start = time.perf_counter()
            try:
                settle_report = await wait_for_settle(self._page, self._config.settle, intent="observe")
            except SettleTimeoutError:
                settle_timed_out = True
                settle_report = None
                self._trace.add(
                    "observe_warning",
                    {
                        "kind": "settle_timeout",
                        "attempt": attempt,
                        "mode": mode,
                    },
                )
            settle_ms = int((time.perf_counter() - settle_start) * 1000)
            if settle_report:
                self._trace.add(
                    "settle",
                    {
                        "intent": "observe",
                        "durations_ms": settle_report.durations_ms,
                        "instability": settle_report.instability,
                    },
                )
            observe_start = time.perf_counter()
            observation, id_map = await observe_page(
                session_id=self._session_id,
                page=self._page,
                mode=mode,
                config=self._config,
                previous_observation=self._current_observation,
                previous_ids=self._id_map,
                expanded=expanded,
            )
            observe_ms = int((time.perf_counter() - observe_start) * 1000)
            if attempt < max_attempts and self._is_no_visible_nodes_state(observation):
                await self._page.wait_for_timeout(300 + (attempt * 200))
                continue
            break

        if observation is None:
            raise BrowserNotReadyError("Observation failed: no observation payload produced.")
        if settle_timed_out and "settle timeout" not in {r.lower() for r in observation.confidence.reasons}:
            observation.confidence.reasons.append("settle timeout")

        self._id_map = id_map
        self._current_observation = observation
        if observation.page.url:
            if not self._url_history or self._url_history[-1] != observation.page.url:
                self._url_history.append(observation.page.url)
        self._trace.add(
            "observe",
            {
                "mode": mode,
                "expanded": expanded,
                "actions": len(observation.available_actions),
                "recovery_attempts": max(0, attempt - 1),
                "settle_ms": settle_ms,
                "observe_ms": observe_ms,
                "settle_timed_out": settle_timed_out,
            },
        )
        return observation

    async def inspect(self, target_id: str, mode: str = "auto") -> dict[str, Any]:
        del mode
        obs = self._current_observation or await self.observe(mode="summary")
        region = next((r for r in obs.regions if r.id == target_id), None)
        if region:
            return {"kind": "region", "region": region.model_dump()}
        form = next((f for f in obs.forms if f.id == target_id), None)
        if form:
            return {"kind": "form", "form": form.model_dump()}
        group = next((g for g in obs.content_groups if g.id == target_id), None)
        if group:
            return {"kind": "content_group", "content_group": group.model_dump()}
        action = next((a for a in obs.available_actions if a.id == target_id), None)
        if action:
            return {"kind": "action", "action": action.model_dump()}
        return {"kind": "unknown", "target_id": target_id}

    async def act(self, request: ActionRequest) -> StepResult:
        if request.action_id == _SEE_MORE_ID:
            return await self._handle_see_more(request)

        self._last_expanded = False
        obs_before = self._current_observation or await self.observe(mode="summary")
        resolve_start = time.perf_counter()
        try:
            action = resolve_action(request, obs_before)
        except ActionStaleError as exc:
            empty_delta = build_delta(obs_before, obs_before)
            execution = build_execution(
                request.op or "unknown",
                False,
                str(exc),
                obs_before,
                obs_before,
                empty_delta,
            )
            return StepResult(
                request=request,
                status="stale",
                message=str(exc),
                execution=execution,
                observation=obs_before,
                delta=empty_delta,
            )
        except ActionNotFoundError as exc:
            empty_delta = build_delta(obs_before, obs_before)
            execution = build_execution(
                request.op or "unknown",
                False,
                str(exc),
                obs_before,
                obs_before,
                empty_delta,
            )
            return StepResult(
                request=request,
                status="invalid",
                message=str(exc),
                execution=execution,
                observation=obs_before,
                delta=empty_delta,
            )
        resolve_ms = int((time.perf_counter() - resolve_start) * 1000)
        self._trace.add("action_request", self._safe_action_payload(request))
        self._trace.add(
            "action_stage",
            {
                "stage": "resolve",
                "resolve_ms": resolve_ms,
                "action_id": action.id,
                "locator_chain": action.locator_recipe,
                "target_fingerprint": action.target_id,
                "retry_attempts": 0,
            },
        )
        execute_start = time.perf_counter()
        try:
            outcome = await execute_action(self._page, action, request)
            ok, message = outcome.ok, outcome.message
        except ActionExecutionError as exc:
            self._trace.add(
                "action_error",
                {"stage": "execute", "error_type": type(exc).__name__, "message": str(exc), "action_id": action.id},
            )
            empty_delta = build_delta(obs_before, obs_before)
            execution = build_execution(action.op, False, str(exc), obs_before, obs_before, empty_delta)
            return StepResult(
                request=request,
                status="failed",
                message=str(exc),
                execution=execution,
                observation=obs_before,
                delta=empty_delta,
            )
        execute_ms = int((time.perf_counter() - execute_start) * 1000)
        settle_timed_out = False
        settle_start = time.perf_counter()
        try:
            settle_report = await wait_for_settle(
                self._page,
                self._config.settle,
                intent="navigation" if action.op in {"open", "submit", "navigate"} else "action",
            )
        except SettleTimeoutError:
            settle_timed_out = True
            settle_report = None
            self._trace.add(
                "action_warning",
                {"stage": "post_action_settle", "kind": "settle_timeout", "action_id": action.id},
            )
        settle_ms = int((time.perf_counter() - settle_start) * 1000)
        if settle_report:
            self._trace.add(
                "settle",
                {
                    "intent": "post_action",
                    "durations_ms": settle_report.durations_ms,
                    "instability": settle_report.instability,
                },
            )
        obs_after = await self.observe(mode="delta")
        if settle_timed_out and message:
            message = f"{message}; settle timeout"
        delta = build_delta(obs_before, obs_after)
        status = classify_status(ok, message, delta)
        execution = build_execution(
            action.op,
            ok,
            message,
            obs_before,
            obs_after,
            delta,
            effect_hint=outcome.effect_hint,
            evidence=outcome.evidence,
        )
        result = StepResult(
            request=request,
            status=status,
            message=message,
            execution=execution,
            observation=obs_after,
            delta=delta,
        )
        self._trace.add(
            "action_result",
            {
                "status": status,
                "message": message,
                "resolve_ms": resolve_ms,
                "execute_ms": execute_ms,
                "settle_ms": settle_ms,
                "effect": execution.effect,
                "new_tab": bool(outcome.evidence.get("new_tab")),
                "evidence": outcome.evidence,
                "delta_materiality": delta.materiality,
            },
        )
        return result

    async def _handle_see_more(self, request: ActionRequest) -> StepResult:
        """Re-observe with expanded=True showing all available actions.

        If the previous observation was already expanded, return the same
        observation with a hint to choose from the existing list instead.
        """
        obs_before = self._current_observation or await self.observe(mode="summary")

        if self._last_expanded:
            empty_delta = build_delta(obs_before, obs_before)
            execution = build_execution("see_more", True, "already expanded", obs_before, obs_before, empty_delta)
            return StepResult(
                request=request,
                status="success",
                message="Already showing all actions. Choose from the list or try a different approach.",
                execution=execution,
                observation=obs_before,
                delta=empty_delta,
            )

        observation = await self.observe(mode="auto", expanded=True)
        self._last_expanded = True
        delta = build_delta(obs_before, observation)
        return StepResult(
            request=request,
            status="success",
            message="Expanded view: showing all available actions.",
            execution=build_execution("see_more", True, "expanded action list", obs_before, observation, delta),
            observation=observation,
            delta=delta,
        )

    async def navigate(self, url: str) -> StepResult:
        if not self._page:
            raise BrowserNotReadyError("No page bound to runtime.")
        before = self._current_observation
        req = ActionRequest(op="navigate", value=url)
        try:
            await self._page.goto(url, wait_until="domcontentloaded", timeout=20000)
        except TypeError:
            await self._page.goto(url)
        except Exception:
            # Some sites never reach full load due long-polling/ads. Retry with looser wait.
            await self._page.goto(url, wait_until="commit", timeout=20000)
        observation = await self.observe(mode="summary")
        execution = build_execution(
            "navigate",
            True,
            f"navigated to {url}",
            before or observation,
            observation,
            build_delta(before, observation),
            effect_hint="navigation",
        )
        return StepResult(
            request=req,
            status="success",
            message=f"navigated to {url}",
            execution=execution,
            observation=observation,
            delta=build_delta(before, observation),
        )

    async def back(self) -> StepResult:
        req = ActionRequest(op="back")
        before = self._current_observation
        await self._page.go_back()
        observation = await self.observe(mode="delta")
        return StepResult(
            request=req,
            status="success",
            message="went back",
            execution=build_execution(
                "back", True, "went back", before or observation, observation, build_delta(before, observation)
            ),
            observation=observation,
            delta=build_delta(before, observation),
        )

    async def forward(self) -> StepResult:
        req = ActionRequest(op="forward")
        before = self._current_observation
        await self._page.go_forward()
        observation = await self.observe(mode="delta")
        return StepResult(
            request=req,
            status="success",
            message="went forward",
            execution=build_execution(
                "forward",
                True,
                "went forward",
                before or observation,
                observation,
                build_delta(before, observation),
            ),
            observation=observation,
            delta=build_delta(before, observation),
        )

    async def reload(self) -> StepResult:
        req = ActionRequest(op="reload")
        before = self._current_observation
        await self._page.reload()
        observation = await self.observe(mode="delta")
        return StepResult(
            request=req,
            status="success",
            message="reloaded",
            execution=build_execution(
                "reload", True, "reloaded", before or observation, observation, build_delta(before, observation)
            ),
            observation=observation,
            delta=build_delta(before, observation),
        )

    async def current_observation(self):
        return self._current_observation

    async def diagnostics(self) -> DiagnosticsReport:
        url = self._page.url if self._page else ""
        return DiagnosticsReport(
            session_id=self._session_id,
            managed=self._managed,
            attached_kind=self._attached_kind,
            ownership_mode=self._ownership_mode,
            current_url=url,
            last_observation_at=(self._current_observation.timestamp if self._current_observation else None),
            trace_events=len(self._trace.events),
            healthy=self._page is not None,
            notes=list(self._profile_warnings),
        )

    async def export_trace(self, path: str) -> str:
        tab_creations = sum(1 for e in self._trace.events if e.get("kind") == "action_result" and e.get("payload", {}).get("new_tab"))
        dialog_events = [
            e for e in self._trace.events if e.get("kind") in {"settle", "action_result"} and "overlay" in json.dumps(e)
        ]
        payload = {
            "session_id": self._session_id,
            "ownership_mode": self._ownership_mode,
            "events": self._trace.events,
            "url_history": self._url_history,
            "tab_creation_count": tab_creations,
            "dialog_stack_events": dialog_events,
            "observation": self._current_observation.model_dump() if self._current_observation else None,
        }
        self._trace.add("trace_export", {"path": path, "bytes": len(json.dumps(payload, default=str))})
        return export_json_bundle(path, payload)

    @staticmethod
    def _safe_action_payload(request: ActionRequest) -> dict[str, Any]:
        payload = request.model_dump()
        if payload.get("value") is not None:
            payload["value"] = "[REDACTED]"
        return payload

    async def close(self) -> None:
        if self._ownership_mode in {"attached_context", "attached_cdp"}:
            warnings.warn(
                f"close() in {self._ownership_mode} does not close externally owned browser; "
                "use force_close_browser() only if you explicitly own the target browser.",
                stacklevel=2,
            )
            if self._ownership_mode == "attached_cdp" and isinstance(self._manager, dict) and "pw" in self._manager:
                await self._manager["pw"].stop()
            return
        if self._manager:
            if hasattr(self._manager, "close"):
                await self._manager.close()
            elif isinstance(self._manager, dict):
                try:
                    if self._manager.get("browser") is not None:
                        await self._manager["browser"].close()
                finally:
                    if self._manager.get("pw") is not None:
                        await self._manager["pw"].stop()

    async def force_close_browser(self) -> None:
        self._trace.add("force_close", {"ownership_mode": self._ownership_mode})
        if self._manager and hasattr(self._manager, "close"):
            await self._manager.close()
            return
        if isinstance(self._manager, dict):
            try:
                if self._manager.get("browser") is not None:
                    await self._manager["browser"].close()
            finally:
                if self._manager.get("pw") is not None:
                    await self._manager["pw"].stop()
