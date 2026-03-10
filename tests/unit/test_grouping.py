from semantic_browser.extractor.grouping import build_content_groups, build_regions


def test_build_regions_from_landmarks():
    nodes = [
        {"tag": "main", "role": "main", "name": "Main", "in_viewport": True, "text": "Main text"},
        {"tag": "nav", "role": "navigation", "name": "Nav", "in_viewport": True, "text": "Nav text"},
    ]
    regions = build_regions(nodes)
    assert len(regions) >= 2


def test_build_content_groups_from_list_items():
    nodes = [
        {"tag": "li", "role": "listitem", "name": "A", "text": "A"},
        {"tag": "li", "role": "listitem", "name": "B", "text": "B"},
        {"tag": "li", "role": "listitem", "name": "C", "text": "C"},
    ]
    groups = build_content_groups(nodes)
    assert len(groups) >= 1
