from __future__ import annotations

import random
import time
from collections import Counter
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import MFProviderState, MFIngestionTask

settings = get_settings()


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


class RateLimiter:
    """
    Simple single-process rate limiter based on per-request spacing.

    We intentionally keep this conservative and synchronous: the scheduler
    and pipelines run in a single process and we want predictable pacing
    to reduce IP-block risk.
    """

    def __init__(self, *, rpm: int, jitter_low: float = 0.8, jitter_high: float = 1.4) -> None:
        self._rpm = max(1, int(rpm))
        self._base_spacing_s = 60.0 / float(self._rpm)
        self._jitter_low = float(jitter_low)
        self._jitter_high = float(jitter_high)
        self._next_allowed = 0.0

    def set_rpm(self, rpm: int) -> None:
        self._rpm = max(1, int(rpm))
        self._base_spacing_s = 60.0 / float(self._rpm)

    def wait(self) -> float:
        now = time.time()
        if now < self._next_allowed:
            delay = self._next_allowed - now
            time.sleep(delay)
        else:
            delay = 0.0

        jitter = random.uniform(self._jitter_low, self._jitter_high)
        self._next_allowed = time.time() + (self._base_spacing_s * jitter)
        return delay


_limiters: dict[tuple[str, str], RateLimiter] = {}


def get_limiter(provider: str, bucket: str) -> RateLimiter:
    key = (provider, bucket)
    lim = _limiters.get(key)
    if lim:
        return lim

    if provider == "mfdata":
        if bucket == "nav":
            rpm = settings.MF_MAX_RPM_MFDATA_NAV
        elif bucket == "analytics":
            rpm = settings.MF_MAX_RPM_MFDATA_ANALYTICS
        else:
            rpm = settings.MF_MAX_RPM_MFDATA_STANDARD
    elif provider == "mfapi":
        rpm = settings.MF_MAX_RPM_MFAPI
    else:
        rpm = 30

    lim = RateLimiter(rpm=rpm)
    _limiters[key] = lim
    return lim


def _get_provider_state(db: Session, provider: str) -> MFProviderState:
    st = db.query(MFProviderState).filter_by(provider=provider).first()
    if st:
        return st
    st = MFProviderState(provider=provider, consecutive_failures=0)
    db.add(st)
    db.commit()
    db.refresh(st)
    return st


def provider_is_paused(db: Session, provider: str) -> bool:
    st = _get_provider_state(db, provider)
    if st.paused_until and st.paused_until > _now_utc():
        return True
    return False


def pause_provider(db: Session, provider: str, *, minutes: int, reason: str | None = None) -> MFProviderState:
    st = _get_provider_state(db, provider)
    st.paused_until = _now_utc() + timedelta(minutes=int(minutes))
    if reason:
        st.last_error = reason[:1000]
    st.updated_at = _now_utc()
    db.add(st)
    db.commit()
    db.refresh(st)
    return st


def resume_provider(db: Session, provider: str) -> MFProviderState:
    st = _get_provider_state(db, provider)
    st.paused_until = None
    st.consecutive_failures = 0
    st.updated_at = _now_utc()
    db.add(st)
    db.commit()
    db.refresh(st)
    return st


def record_provider_success(db: Session, provider: str) -> None:
    st = _get_provider_state(db, provider)
    if st.consecutive_failures != 0 or st.last_error:
        st.consecutive_failures = 0
        st.last_error = None
        st.updated_at = _now_utc()
        db.add(st)
        db.commit()


def record_provider_failure(db: Session, provider: str, error: str) -> MFProviderState:
    st = _get_provider_state(db, provider)
    st.consecutive_failures = int(st.consecutive_failures or 0) + 1
    st.last_error = (error or "unknown error")[:1000]
    st.updated_at = _now_utc()

    if st.consecutive_failures >= settings.MF_PROVIDER_FAIL_THRESHOLD:
        minutes = random.randint(settings.MF_PROVIDER_PAUSE_MIN_MINUTES, settings.MF_PROVIDER_PAUSE_MAX_MINUTES)
        st.paused_until = _now_utc() + timedelta(minutes=minutes)
    db.add(st)
    db.commit()
    db.refresh(st)
    return st


RETRIABLE_STATUS = {429, 500, 502, 503, 504}
STRESS_STATUS = {403, 429, 503}


@dataclass
class RequestResult:
    status_code: int | None
    json: Any | None
    text: str | None


class IngestionTask:
    """
    Records a unit of work under a run: counts, retries, backoff, and status histogram.
    """

    def __init__(
        self,
        db: Session,
        *,
        run_id: str | None,
        provider: str,
        endpoint_class: str,
        scheme_code: int | None = None,
        family_id: int | None = None,
    ) -> None:
        self.db = db
        self.provider = provider
        self.endpoint_class = endpoint_class
        self.scheme_code = scheme_code
        self.family_id = family_id
        self._client: httpx.Client | None = None
        self._status_counter: Counter[int] = Counter()
        self._request_count = 0
        self._retry_count = 0
        self._backoff_s = 0.0

        self.row = MFIngestionTask(
            run_id=run_id,
            provider=provider,
            endpoint_class=endpoint_class,
            scheme_code=scheme_code,
            family_id=family_id,
            status="running",
            started_at=_now_utc(),
        )
        db.add(self.row)
        db.commit()
        db.refresh(self.row)

    def close(self) -> None:
        if self._client:
            self._client.close()
            self._client = None

    def _http_client(self) -> httpx.Client:
        if self._client:
            return self._client
        timeout = httpx.Timeout(
            connect=settings.MF_HTTP_CONNECT_TIMEOUT_S,
            read=settings.MF_HTTP_READ_TIMEOUT_S,
            write=settings.MF_HTTP_READ_TIMEOUT_S,
            pool=settings.MF_HTTP_READ_TIMEOUT_S,
        )
        self._client = httpx.Client(
            timeout=timeout,
            follow_redirects=True,
            headers={"User-Agent": settings.MF_HTTP_USER_AGENT},
        )
        return self._client

    def finish(self, *, ok: bool, error: str | None = None, status: str | None = None) -> None:
        self.row.finished_at = _now_utc()
        self.row.status = status or ("success" if ok else "failed")
        self.row.request_count = int(self._request_count)
        self.row.retry_count = int(self._retry_count)
        self.row.backoff_seconds = float(self._backoff_s)
        self.row.http_statuses = dict(self._status_counter)
        self.row.error_text = (error[:4000] if error else None)
        self.db.add(self.row)
        self.db.commit()
        self.close()

    def request(
        self,
        *,
        method: str,
        url: str,
        bucket: str,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        max_retries: int = 3,
    ) -> RequestResult:
        if provider_is_paused(self.db, self.provider):
            self.finish(ok=True, status="skipped", error=f"Provider paused: {self.provider}")
            return RequestResult(status_code=None, json=None, text=None)

        limiter = get_limiter(self.provider, bucket)
        client = self._http_client()

        attempt = 0
        while True:
            attempt += 1

            limiter.wait()
            self._request_count += 1

            try:
                r = client.request(method.upper(), url, params=params, headers=headers)
                self._status_counter[int(r.status_code)] += 1

                # Honor provider rate-limit headers when present (best-effort).
                if self.provider == "mfdata":
                    _maybe_honor_rate_limit_headers(r, self)

                if r.status_code in STRESS_STATUS:
                    record_provider_failure(self.db, self.provider, f"HTTP {r.status_code} from {url}")

                if r.status_code >= 400:
                    # Retry only for network/5xx/429 and selected stress signals.
                    if r.status_code in RETRIABLE_STATUS and attempt <= max_retries:
                        self._retry_count += 1
                        backoff = _compute_backoff_s(attempt)
                        self._backoff_s += backoff
                        time.sleep(backoff)
                        continue
                    r.raise_for_status()

                record_provider_success(self.db, self.provider)
                js = None
                txt = None
                ct = (r.headers.get("content-type") or "").lower()
                if "application/json" in ct:
                    js = r.json()
                else:
                    txt = r.text
                return RequestResult(status_code=int(r.status_code), json=js, text=txt)
            except (httpx.TimeoutException, httpx.TransportError) as e:
                record_provider_failure(self.db, self.provider, str(e))
                if attempt <= max_retries:
                    self._retry_count += 1
                    backoff = _compute_backoff_s(attempt)
                    self._backoff_s += backoff
                    time.sleep(backoff)
                    continue
                raise


def _compute_backoff_s(attempt: int) -> float:
    # 5s, 10s, 20s, 60s, 300s... with jitter
    steps = [5, 10, 20, 60, 300]
    base = steps[min(attempt - 1, len(steps) - 1)]
    return float(base) * random.uniform(0.8, 1.4)


def _maybe_honor_rate_limit_headers(r: httpx.Response, t: IngestionTask) -> None:
    """
    mfdata.in returns rate-limit headers; use them defensively.
    We avoid making assumptions about units; treat reset as seconds if small,
    or epoch seconds if large.
    """
    try:
        remaining_raw = r.headers.get("X-RateLimit-Remaining")
        if remaining_raw is None:
            return
        remaining = int(float(remaining_raw))
        if remaining > 1:
            return

        reset_raw = r.headers.get("X-RateLimit-Reset") or r.headers.get("X-RateLimit-Reset-Seconds")
        if not reset_raw:
            # Gentle pause if we are likely at the edge.
            t._backoff_s += 2.0
            time.sleep(2.0)
            return

        val = float(reset_raw)
        if val > 1_000_000_000:
            # epoch seconds
            wait_s = max(0.0, val - time.time())
        else:
            # seconds until reset (best guess)
            wait_s = max(0.0, val)
        wait_s = min(wait_s, 90.0)
        if wait_s > 0:
            t._backoff_s += wait_s
            time.sleep(wait_s)
    except Exception:
        return


@contextmanager
def task(
    db: Session,
    *,
    run_id: str | None,
    provider: str,
    endpoint_class: str,
    scheme_code: int | None = None,
    family_id: int | None = None,
):
    t = IngestionTask(
        db,
        run_id=run_id,
        provider=provider,
        endpoint_class=endpoint_class,
        scheme_code=scheme_code,
        family_id=family_id,
    )
    try:
        yield t
        t.finish(ok=True)
    except Exception as e:
        t.finish(ok=False, error=str(e))
        raise
