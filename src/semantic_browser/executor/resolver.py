"""Locator resolution from action metadata."""

from __future__ import annotations

from semantic_browser.models import ActionDescriptor


async def resolve_locator(page, action: ActionDescriptor):
    recipe = action.locator_recipe
    name = (recipe.get("name") or "").strip()
    role = (recipe.get("role") or "").strip()
    tag = (recipe.get("tag") or "").strip()
    if role in {"button", "link", "textbox", "checkbox", "combobox", "searchbox"} and name:
        try:
            return page.get_by_role(role, name=name).first
        except Exception:
            pass
    if tag in {"input", "textarea", "select"} and name:
        try:
            return page.get_by_label(name).first
        except Exception:
            pass
    if name:
        return page.get_by_text(name).first
    return page.locator("body")
