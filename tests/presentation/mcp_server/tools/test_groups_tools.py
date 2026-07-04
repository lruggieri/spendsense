def test_create_and_list_groups(svcs_and_path):
    svcs, _ = svcs_and_path
    ok, msg, gid = svcs.group.create_group("Travel")
    assert ok, msg
    groups = svcs.group.get_all_groups()
    assert any(g.name == "Travel" for g in groups)
