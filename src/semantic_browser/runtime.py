"""Primary runtime API."""

from __future__ import annotations

import json
import uuid
from typing import Any

from semantic_browser.config import RuntimeConfig
from semantic_browser.errors import ActionExecutionError, ActionNotFoundError, ActionStaleError, AttachmentError, BrowserNotReadyError
from semantic_browser.executor.actions import execute_action
from semantic_browser.executor.results import build_execution, classify_status
from semantic_browser.executor.validation import resolve_action
from semantic_browser.extractor.diff import build_delta
from semantic_browser.extractor.engine import observe_page
from semantic_browser.extractor.settle import wait_for_settle
from semantic_browser.models import ActionRequest, DiagnosticsReport, Observation, StepResult
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
    ) -> None:
        self._page = page
        self._config = config or RuntimeConfig()
        self._managed = managed
        self._manager = manager
        self._attached_kind = attached_kind
        self._session_id = str(uuid.uuid4())
        self._current_observation: Observation | None = None
        self._id_map: dict[str, str] = {}
        self._trace = TraceStore(max_events=self._config.telemetry.max_events)

    @classmethod
    def from_page(cls, page: Any, config: RuntimeConfig | None = None, profile_registry=None):
        del profile_registry
        if page is None:
            raise AttachmentError("Cannot attach to null page.")
        return cls(page=page, config=config, managed=False, attached_kind="page")

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
        return cls(page=page, config=config, managed=False, attached_kind="context")

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
            return cls(page=page, config=config, managed=True, manager={"pw": pw, "browser": browser})
        except Exception as exc:
            try:
                await pw.stop()
            finally:
                pass
            raise AttachmentError(f"Failed CDP attach at {endpoint}: {exc}") from exc

    @property
    def session_id(self) -> str:
        return self._session_id

    @staticmethod
    def _is_no_visible_nodes_state(observation: Observation) -> bool:
        reasons = {r.lower() for r in observation.confidence.reasons}
        return "no visible nodes" in reasons or (
            len(observation.available_actions) == 0 and observation.confidence.overall <= 0.2
        )

    async def observe(self, mode: str = "summary") -> Observation:
        max_attempts = 3 if mode == "summary" else 1
        observation: Observation | None = None
        id_map: dict[str, str] = {}
        for attempt in range(1, max_attempts + 1):
            await wait_for_settle(self._page, self._config.settle)
            observation, id_map = await observe_page(
                session_id=self._session_id,
                page=self._page,
                mode=mode,
                config=self._config,
                previous_observation=self._current_observation,
                previous_ids=self._id_map,
            )
            if attempt < max_attempts and self._is_no_visible_nodes_state(observation):
                if attempt == 1:
                    await self._page.wait_for_timeout(350)
                else:
                    try:
                        await self._page.reload(wait_until="domcontentloaded")
                    except TypeError:
                        await self._page.reload()
                    await self._page.wait_for_timeout(700)
                continue
            break

        self._id_map = id_map
        self._current_observation = observation
        self._trace.add(
            "observe",
            {
                "mode": mode,
                "actions": len(observation.available_actions),
                "recovery_attempts": max(0, attempt - 1),
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
        obs_before = self._current_observation or await self.observe(mode="summary")
        try:
            action = resolve_action(request, obs_before)
        except ActionStaleError as exc:
            execution = build_execution(request.op or "unknown", False, str(exc), obs_before)
            return StepResult(
                request=request,
                status="stale",
                message=str(exc),
                execution=execution,
                observation=obs_before,
                delta=build_delta(obs_before, obs_before),
            )
        except ActionNotFoundError as exc:
            execution = build_execution(request.op or "unknown", False, str(exc), obs_before)
            return StepResult(
                request=request,
                status="invalid",
                message=str(exc),
                execution=execution,
                observation=obs_before,
                delta=build_delta(obs_before, obs_before),
            )
        self._trace.add("action_request", request.model_dump())
        try:
            ok, message = await execute_action(self._page, action, request)
        except ActionExecutionError as exc:
            execution = build_execution(action.op, False, str(exc), obs_before)
            return StepResult(
                request=request,
                status="failed",
                message=str(exc),
                execution=execution,
                observation=obs_before,
                delta=build_delta(obs_before, obs_before),
            )
        await wait_for_settle(self._page, self._config.settle)
        obs_after = await self.observe(mode="delta")
        delta = build_delta(obs_before, obs_after)
        status = classify_status(ok, message, delta)
        execution = build_execution(action.op, ok, message, obs_after)
        result = StepResult(
            request=request,
            status=status,
            message=message,
            execution=execution,
            observation=obs_after,
            delta=delta,
        )
        self._trace.add("action_result", {"status": status, "message": message})
        return result

    async def navigate(self, url: str) -> StepResult:
        if not self._page:
            raise BrowserNotReadyError("No page bound to runtime.")
        before = self._current_observation
        req = ActionRequest(op="navigate", value=url)
        await self._page.goto(url)
        observation = await self.observe(mode="summary")
        execution = build_execution("navigate", True, f"navigated to {url}", observation)
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
            execution=build_execution("back", True, "went back", observation),
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
            execution=build_execution("forward", True, "went forward", observation),
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
            execution=build_execution("reload", True, "reloaded", observation),
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
            current_url=url,
            last_observation_at=(self._current_observation.timestamp if self._current_observation else None),
            trace_events=len(self._trace.events),
            healthy=self._page is not None,
            notes=[],
        )

    async def export_trace(self, path: str) -> str:
        payload = {
            "session_id": self._session_id,
            "events": self._trace.events,
            "observation": self._current_observation.model_dump() if self._current_observation else None,
        }
        self._trace.add("trace_export", {"path": path, "bytes": len(json.dumps(payload, default=str))})
        return export_json_bundle(path, payload)

    async def close(self) -> None:
        if self._managed and self._manager:
            if hasattr(self._manager, "close"):
                await self._manager.close()
            elif isinstance(self._manager, dict):
                try:
                    await self._manager["browser"].close()
                finally:
                    await self._manager["pw"].stop()
