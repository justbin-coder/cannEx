import time
from webchat.cannex_chat.middleware.rate_limit import RateLimiter


def test_allow_within_limit():
    rl = RateLimiter(max_per_window=3, window_seconds=60)
    assert rl.allow("ip1")
    assert rl.allow("ip1")
    assert rl.allow("ip1")


def test_block_over_limit():
    rl = RateLimiter(max_per_window=2, window_seconds=60)
    assert rl.allow("ip1")
    assert rl.allow("ip1")
    assert rl.allow("ip1") is False


def test_separate_ips():
    rl = RateLimiter(max_per_window=1, window_seconds=60)
    assert rl.allow("ipA")
    assert rl.allow("ipA") is False
    assert rl.allow("ipB")


def test_window_expires():
    rl = RateLimiter(max_per_window=1, window_seconds=0.1)
    assert rl.allow("ip1")
    assert rl.allow("ip1") is False
    time.sleep(0.15)
    assert rl.allow("ip1")
