"""Corpus scoring helpers."""

from __future__ import annotations

from typing import Any


def score_site_result(entry: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    min_actions = int(entry.get("min_actions", 1))
    expected_types = set(entry.get("expected_page_types", []))
    observed_type = result.get("page_type")
    action_count = int(result.get("action_count", 0))
    action_pass = action_count >= min_actions
    type_pass = not expected_types or observed_type in expected_types
    score = 0.0
    if action_pass:
        score += 0.5
    if type_pass:
        score += 0.5
    return {
        "site": entry.get("site"),
        "url": entry.get("url"),
        "action_count": action_count,
        "min_actions": min_actions,
        "observed_page_type": observed_type,
        "expected_page_types": sorted(list(expected_types)),
        "passed": bool(action_pass and type_pass),
        "score": score,
    }


def aggregate_report(site_scores: list[dict[str, Any]]) -> dict[str, Any]:
    thresholds = {
        "semantic_coverage_min": 0.85,
        "action_execution_min": 0.90,
        "stable_id_persistence_min": 0.95,
        "blocker_detection_min": 0.90,
    }
    if not site_scores:
        return {
            "site_count": 0,
            "pass_rate": 0.0,
            "avg_score": 0.0,
            "sites": [],
            "thresholds": thresholds,
            "meets_thresholds": False,
        }
    passed = sum(1 for s in site_scores if s.get("passed"))
    avg_score = sum(float(s.get("score", 0.0)) for s in site_scores) / len(site_scores)
    pass_rate = passed / len(site_scores)
    return {
        "site_count": len(site_scores),
        "pass_rate": pass_rate,
        "avg_score": avg_score,
        "sites": site_scores,
        "thresholds": thresholds,
        "meets_thresholds": pass_rate >= thresholds["action_execution_min"],
    }
