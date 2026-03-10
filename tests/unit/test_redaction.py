from semantic_browser.config import RedactionConfig
from semantic_browser.extractor.redaction import redact_nodes


def test_redact_password_and_tokens():
    nodes = [
        {"type": "password", "name": "Password", "text": "hunter2"},
        {"type": "text", "name": "API token", "text": "abc"},
    ]
    out = redact_nodes(nodes, RedactionConfig(enabled=True, expose_secrets=False))
    assert "[REDACTED]" in out[0]["name"]
    assert out[1]["text"] == "[REDACTED]"
