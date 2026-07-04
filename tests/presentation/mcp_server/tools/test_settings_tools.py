def test_get_user_settings_returns_expected_keys(svcs_and_path):
    svcs, _ = svcs_and_path
    s = svcs.user_settings.get_user_settings()
    # UserSettings always has currency and language
    assert hasattr(s, "currency")
    assert hasattr(s, "language")
