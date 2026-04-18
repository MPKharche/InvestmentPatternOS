from __future__ import annotations

from datetime import datetime, timezone, timedelta

import app.mf.safety as safety


class _FakeDB:
    def add(self, _obj):  # noqa: ANN001
        return None

    def commit(self):
        return None

    def refresh(self, _obj):  # noqa: ANN001
        return None


class _State:
    def __init__(self):
        self.provider = "mfdata"
        self.paused_until = None
        self.consecutive_failures = 0
        self.last_error = None
        self.updated_at = None


def test_rate_limiter_wait_is_jittered_and_respects_spacing(monkeypatch):
    t = {"now": 0.0}
    slept: list[float] = []

    monkeypatch.setattr(safety.time, "time", lambda: t["now"])
    monkeypatch.setattr(safety.time, "sleep", lambda s: slept.append(float(s)))

    lim = safety.RateLimiter(rpm=60, jitter_low=1.0, jitter_high=1.0)  # 1 req/sec
    lim.wait()
    assert slept == []

    # Halfway to the next slot: should sleep ~0.5s.
    t["now"] = 0.5
    lim.wait()
    assert slept and abs(slept[-1] - 0.5) < 1e-9


def test_compute_backoff_increases(monkeypatch):
    monkeypatch.setattr(safety.random, "uniform", lambda a, b: 1.0)
    b1 = safety._compute_backoff_s(1)
    b2 = safety._compute_backoff_s(2)
    b3 = safety._compute_backoff_s(3)
    assert b1 == 5.0
    assert b2 == 10.0
    assert b3 == 20.0


def test_circuit_breaker_pauses_after_threshold(monkeypatch):
    st = _State()
    db = _FakeDB()

    fixed_now = datetime(2026, 4, 17, 0, 0, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(safety, "_now_utc", lambda: fixed_now)
    monkeypatch.setattr(safety, "_get_provider_state", lambda _db, _provider: st)
    monkeypatch.setattr(safety.random, "randint", lambda a, b: 30)

    # Make threshold small and deterministic for the test.
    monkeypatch.setattr(safety.settings, "MF_PROVIDER_FAIL_THRESHOLD", 2)
    monkeypatch.setattr(safety.settings, "MF_PROVIDER_PAUSE_MIN_MINUTES", 30)
    monkeypatch.setattr(safety.settings, "MF_PROVIDER_PAUSE_MAX_MINUTES", 30)

    safety.record_provider_failure(db, "mfdata", "err-1")
    assert st.paused_until is None
    safety.record_provider_failure(db, "mfdata", "err-2")
    assert st.paused_until == fixed_now + timedelta(minutes=30)

