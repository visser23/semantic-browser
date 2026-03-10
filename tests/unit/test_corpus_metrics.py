from semantic_browser.corpus.metrics import aggregate_report, score_site_result


def test_score_site_result_pass():
    entry = {"site": "example", "url": "https://example.com", "expected_page_types": ["generic"], "min_actions": 1}
    result = {"page_type": "generic", "action_count": 3}
    score = score_site_result(entry, result)
    assert score["passed"] is True


def test_aggregate_report():
    report = aggregate_report([{"passed": True, "score": 1.0}, {"passed": False, "score": 0.5}])
    assert report["site_count"] == 2
    assert report["pass_rate"] == 0.5
    assert "thresholds" in report
