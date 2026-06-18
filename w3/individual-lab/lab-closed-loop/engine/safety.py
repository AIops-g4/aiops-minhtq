"""Blast-radius and circuit-breaker primitives."""

from __future__ import annotations

import time
from collections import defaultdict, deque
from dataclasses import dataclass, field


@dataclass
class BlastRadiusGuard:
    """In-memory action rate limiter for the current orchestrator process."""

    max_actions_per_minute: int
    max_restarts_per_service_per_hour: int
    global_window: deque[float] = field(default_factory=deque)
    service_restart_windows: dict[str, deque[float]] = field(
        default_factory=lambda: defaultdict(deque)
    )

    @staticmethod
    def _prune(window: deque[float], horizon: float) -> None:
        while window and window[0] < horizon:
            window.popleft()

    def check(self, service: str, runbook: str) -> tuple[bool, str]:
        now = time.time()
        self._prune(self.global_window, now - 60)
        self._prune(self.service_restart_windows[service], now - 3600)

        if len(self.global_window) >= self.max_actions_per_minute:
            return False, "max_actions_per_minute"
        if "restart" in runbook and (
            len(self.service_restart_windows[service])
            >= self.max_restarts_per_service_per_hour
        ):
            return False, "max_restarts_per_service_per_hour"
        return True, "ok"

    def record(self, service: str, runbook: str) -> None:
        now = time.time()
        self.global_window.append(now)
        if "restart" in runbook:
            self.service_restart_windows[service].append(now)

    def remaining_global_actions(self) -> int:
        self._prune(self.global_window, time.time() - 60)
        return max(0, self.max_actions_per_minute - len(self.global_window))


@dataclass
class CircuitBreaker:
    """Open after N consecutive action or verify failures."""

    threshold: int
    failures: int = 0
    open: bool = False

    def is_open(self) -> bool:
        return self.open

    def record_success(self) -> None:
        self.failures = 0

    def record_failure(self) -> bool:
        self.failures += 1
        if self.failures >= self.threshold:
            self.open = True
        return self.open
