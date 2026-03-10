from semantic_browser.config import ExtractionConfig
from semantic_browser.extractor.blockers import confidence_from_nodes, detect_blockers


def test_detect_cookie_blocker():
    nodes = [{"name": "Cookie consent", "text": "Accept all cookies", "tag": "div", "role": "dialog"}]
    blockers = detect_blockers(nodes)
    assert any(b.kind == "cookie_banner" for b in blockers)


def test_unreliability_warning_for_low_named_ratio():
    nodes = [{"name": "", "text": "", "tag": "button", "role": "button"} for _ in range(10)]
    _confidence, warnings = confidence_from_nodes(nodes, actions_count=1, cfg=ExtractionConfig())
    assert any(w.kind == "low_semantic_quality" for w in warnings)
