"""Sensitive data redaction helpers."""

from __future__ import annotations

from semantic_browser.config import RedactionConfig

SENSITIVE_TOKENS = ("token", "secret", "api key", "auth", "bearer", "cvv", "card")


def redact_nodes(nodes: list[dict], cfg: RedactionConfig) -> list[dict]:
    if not cfg.enabled or cfg.expose_secrets:
        return nodes
    redacted: list[dict] = []
    for node in nodes:
        n = dict(node)
        node_type = (n.get("type") or "").lower()
        name = (n.get("name") or "").lower()
        text = (n.get("text") or "").lower()
        if node_type == "password":
            n["name"] = "Password [REDACTED]"
            n["text"] = ""
        elif any(tok in name or tok in text for tok in SENSITIVE_TOKENS):
            n["text"] = "[REDACTED]"
        redacted.append(n)
    return redacted
