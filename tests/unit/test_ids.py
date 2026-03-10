from semantic_browser.extractor.ids import assign_node_ids, fingerprint_for


def test_fingerprint_stable_for_same_node():
    node = {"role": "button", "tag": "button", "name": "Submit", "type": "", "href": ""}
    assert fingerprint_for(node) == fingerprint_for(node)


def test_assign_node_ids_reuses_previous_map():
    node = {"role": "button", "tag": "button", "name": "Submit", "type": "", "href": ""}
    fp = fingerprint_for(node)
    ids = assign_node_ids([node], previous={fp: "elm-existing"})
    assert ids[fp] == "elm-existing"
