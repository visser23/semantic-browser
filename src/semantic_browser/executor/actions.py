"""Playwright action execution."""

from __future__ import annotations

from dataclasses import dataclass, field

from semantic_browser.errors import ActionExecutionError
from semantic_browser.models import ActionDescriptor, ActionRequest


@dataclass
class ActionExecutionOutcome:
    ok: bool
    message: str
    effect_hint: str = "none"
    evidence: dict[str, object] = field(default_factory=dict)


async def execute_action(page, action: ActionDescriptor, request: ActionRequest) -> ActionExecutionOutcome:
    try:
        before_url = page.url
        context = getattr(page, "context", None)
        if callable(context):
            context = context()
        before_tab_count = len(getattr(context, "pages", []) or [])
        if action.op == "navigate":
            if request.value is None:
                raise ActionExecutionError("navigate requires request.value URL")
            try:
                await page.goto(str(request.value), wait_until="domcontentloaded", timeout=15000)
            except Exception:
                await page.goto(str(request.value), timeout=15000)
            return ActionExecutionOutcome(ok=True, message="navigated", effect_hint="navigation")
        if action.op == "back":
            await page.go_back()
            return ActionExecutionOutcome(ok=True, message="went back", effect_hint="navigation")
        if action.op == "forward":
            await page.go_forward()
            return ActionExecutionOutcome(ok=True, message="went forward", effect_hint="navigation")
        if action.op == "reload":
            await page.reload()
            return ActionExecutionOutcome(ok=True, message="reloaded", effect_hint="navigation")
        if action.op == "click" or action.op == "open":
            locator = await _locator(page, action)
            await locator.click(timeout=5000)
            await page.wait_for_timeout(100)
            context_after = getattr(page, "context", None)
            if callable(context_after):
                context_after = context_after()
            after_tab_count = len(getattr(context_after, "pages", []) or [])
            after_url = page.url
            new_tab = after_tab_count > before_tab_count
            nav = bool(after_url and before_url != after_url)
            effect_hint = "navigation" if (nav or new_tab or action.op == "open") else "state_change"
            return ActionExecutionOutcome(
                ok=True,
                message="clicked",
                effect_hint=effect_hint,
                evidence={"new_tab": new_tab, "before_url": before_url, "after_url": after_url},
            )
        if action.op == "fill":
            locator = await _locator(page, action)
            value = "" if request.value is None else str(request.value)
            clear_strategy = str(request.options.get("clear_strategy", "clear")).lower()
            type_slowly = bool(request.options.get("type_slowly", False))
            if clear_strategy == "append":
                if type_slowly:
                    await locator.type(value, timeout=5000)
                else:
                    await locator.fill((await locator.input_value()) + value, timeout=5000)
            else:
                if type_slowly:
                    await locator.fill("", timeout=5000)
                    await locator.type(value, timeout=5000)
                else:
                    await locator.fill(value, timeout=5000)
            recipe = action.locator_recipe or {}
            input_type = recipe.get("type", "")
            label_lower = (action.label or "").lower()
            is_search = input_type == "search" or "search" in label_lower
            suggestions = await page.evaluate(
                "() => document.querySelectorAll('[role=\"listbox\"],[role=\"menu\"],[aria-expanded=\"true\"]').length"
            )
            if is_search and value:
                await locator.press("Enter")
                return ActionExecutionOutcome(
                    ok=True,
                    message="filled and submitted",
                    effect_hint="content_change",
                    evidence={"suggestion_popups": int(suggestions)},
                )
            return ActionExecutionOutcome(
                ok=True,
                message="filled",
                effect_hint="state_change",
                evidence={"suggestion_popups": int(suggestions)},
            )
        if action.op == "clear":
            locator = await _locator(page, action)
            await locator.fill("", timeout=5000)
            return ActionExecutionOutcome(ok=True, message="cleared", effect_hint="state_change")
        if action.op == "select_option":
            locator = await _locator(page, action)
            await locator.select_option(str(request.value), timeout=5000)
            return ActionExecutionOutcome(ok=True, message="option selected", effect_hint="state_change")
        if action.op == "toggle":
            locator = await _locator(page, action)
            recipe = action.locator_recipe or {}
            toggle_kind = "switch" if recipe.get("role") == "switch" else recipe.get("type", "toggle")
            await locator.click(timeout=5000)
            return ActionExecutionOutcome(
                ok=True,
                message=f"toggled {toggle_kind}",
                effect_hint="state_change",
                evidence={"toggle_kind": toggle_kind},
            )
        if action.op == "press_key":
            await page.keyboard.press(str(request.value or "Enter"))
            return ActionExecutionOutcome(ok=True, message="key pressed", effect_hint="state_change")
        if action.op == "submit":
            locator = await _locator(page, action)
            used_enter = True
            try:
                tag = await locator.evaluate("el => (el.tagName || '').toLowerCase()")
                input_type = await locator.evaluate("el => (el.getAttribute('type') || '').toLowerCase()")
                if tag == "button" or input_type in {"submit", "button", "image"}:
                    await locator.click(timeout=5000)
                    used_enter = False
                else:
                    await locator.press("Enter")
            except Exception:
                await locator.press("Enter")
            return ActionExecutionOutcome(
                ok=True,
                message="submitted",
                effect_hint="content_change",
                evidence={"submit_strategy": "enter" if used_enter else "control"},
            )
        if action.op == "scroll_into_view":
            locator = await _locator(page, action)
            await locator.scroll_into_view_if_needed(timeout=5000)
            return ActionExecutionOutcome(ok=True, message="scrolled", effect_hint="none")
        if action.op == "wait":
            ms = int(request.options.get("ms", request.value or 500))
            await page.wait_for_timeout(ms)
            return ActionExecutionOutcome(ok=True, message="waited", effect_hint="none")
    except Exception as exc:
        raise ActionExecutionError(str(exc)) from exc
    raise ActionExecutionError(f"Unsupported action op: {action.op}")


async def _locator(page, action):
    from semantic_browser.executor.resolver import resolve_locator

    return await resolve_locator(page, action)
