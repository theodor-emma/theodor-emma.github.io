"""Slows down anyone guessing invitation codes.

Only failed lookups (an unknown code) count, so guests opening their own
invitation as often as they like are never affected, even many of them behind
one shared connection. Once an address has too many recent failures, every
code lookup from it is refused until the oldest ones age out.

IPv4 only: an IPv6 visitor can switch between addresses at will, so counting
them would only ever catch honest people. Kept in memory, so a restart clears it.
"""

import ipaddress
import threading
import time
from collections import deque

# (window in seconds, failures allowed in it)
DEFAULT_LIMITS = ((60, 10), (3600, 20))


class FailureLimiter:
    def __init__(self, limits=DEFAULT_LIMITS, max_tracked: int = 10_000):
        self.limits = limits
        self.longest = max(window for window, _ in limits)
        self.max_tracked = max_tracked
        self._failures: dict = {}
        self._lock = threading.Lock()

    @staticmethod
    def address(host: str):
        """The IPv4 address to count, or None for IPv6 and anything unparsable."""
        try:
            ip = ipaddress.ip_address(host or "")
        except ValueError:
            return None
        if ip.version == 6:
            ip = ip.ipv4_mapped     # an IPv4 client seen through an IPv6 socket
        return str(ip) if ip else None

    def _recent(self, address: str, now: float) -> deque:
        times = self._failures.setdefault(address, deque())
        while times and times[0] <= now - self.longest:
            times.popleft()
        return times

    def blocked(self, host: str, now: float = None) -> bool:
        address = self.address(host)
        if address is None:
            return False
        now = time.monotonic() if now is None else now
        with self._lock:
            times = self._recent(address, now)
            return any(
                sum(1 for t in times if t > now - window) >= allowed
                for window, allowed in self.limits
            )

    def record_failure(self, host: str, now: float = None) -> None:
        address = self.address(host)
        if address is None:
            return
        now = time.monotonic() if now is None else now
        with self._lock:
            self._recent(address, now).append(now)
            if len(self._failures) > self.max_tracked:
                self._forget_idle(now)

    def _forget_idle(self, now: float) -> None:
        for address in list(self._failures):
            if not self._recent(address, now):
                del self._failures[address]
        # Still too many: drop the addresses that have been quiet the longest
        if len(self._failures) > self.max_tracked:
            by_last = sorted(self._failures, key=lambda a: self._failures[a][-1])
            for address in by_last[: len(by_last) // 2]:
                del self._failures[address]

    def reset(self) -> None:
        with self._lock:
            self._failures.clear()
