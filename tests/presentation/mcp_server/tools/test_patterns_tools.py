def test_create_and_list_patterns(svcs_and_path):
    svcs, _ = svcs_and_path
    ok, _, cid = svcs.category.create_category("Food", "", "")
    assert ok
    # Check real rule format from PatternService
    rules = [{"operator": "OR", "keyword": "STARBUCKS"}]
    ok2, msg, pid = svcs.pattern.create_pattern(rules, cid, "sbux")
    assert ok2, msg
    pats = svcs.pattern.get_all_patterns()
    assert any(p.get("id") == pid for p in pats)
