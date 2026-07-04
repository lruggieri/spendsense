def test_create_and_list_categories(svcs_and_path):
    svcs, _ = svcs_and_path
    ok, msg, cid = svcs.category.create_category("Food", "", "")
    assert ok, msg
    cats = svcs.category.get_all_categories()
    assert any(c.name == "Food" for c in cats)


def test_create_subcategory(svcs_and_path):
    svcs, _ = svcs_and_path
    ok, _, parent_id = svcs.category.create_category("Food", "", "")
    assert ok
    ok2, _, child_id = svcs.category.create_category("Restaurants", "", parent_id)
    assert ok2
    cats = svcs.category.get_all_categories()
    child = next(c for c in cats if c.id == child_id)
    assert child.parent_id == parent_id
