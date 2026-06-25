from presentation.mcp.ratelimit import RateLimiter


def test_allows_under_limit_then_blocks():
    rl = RateLimiter(limit_per_min=3)
    t = 1000.0
    assert [rl.check("k", t) for _ in range(3)] == [True, True, True]
    assert rl.check("k", t) is False  # 4th within the same minute


def test_window_resets():
    rl = RateLimiter(limit_per_min=1)
    assert rl.check("k", 1000.0) is True
    assert rl.check("k", 1000.0) is False
    assert rl.check("k", 1061.0) is True  # >60s later


def test_keys_are_independent():
    rl = RateLimiter(limit_per_min=1)
    assert rl.check("a", 1000.0) is True
    assert rl.check("b", 1000.0) is True
