"""The code-guessing limiter on its own, with a controlled clock."""

from rate_limit import FailureLimiter

IP = "203.0.113.9"


def fail(limiter, times, at):
    for _ in range(times):
        limiter.record_failure(IP, now=at)


def test_ten_failures_in_a_minute_block_until_they_age_out():
    limiter = FailureLimiter()
    fail(limiter, 9, at=0)
    assert not limiter.blocked(IP, now=1)
    fail(limiter, 1, at=1)
    assert limiter.blocked(IP, now=2)
    assert not limiter.blocked(IP, now=62)


def test_twenty_failures_in_an_hour_block_for_the_hour():
    limiter = FailureLimiter()
    for minute in range(4):
        fail(limiter, 5, at=minute * 120)     # never 10 in one minute
    assert limiter.blocked(IP, now=500)
    assert limiter.blocked(IP, now=3500)
    assert not limiter.blocked(IP, now=3601)


def test_only_ipv4_is_counted():
    limiter = FailureLimiter()
    assert FailureLimiter.address("::ffff:203.0.113.9") == IP
    assert FailureLimiter.address("2001:db8::1") is None
    assert FailureLimiter.address("testclient") is None
    for _ in range(50):
        limiter.record_failure("2001:db8::1", now=0)
    assert not limiter.blocked("2001:db8::1", now=1)
    fail(limiter, 10, at=0)
    assert limiter.blocked("::ffff:203.0.113.9", now=1)


def test_memory_stays_bounded():
    limiter = FailureLimiter(max_tracked=100)
    for i in range(1000):
        limiter.record_failure(f"10.0.{i // 256}.{i % 256}", now=i)
    assert len(limiter._failures) <= 101
