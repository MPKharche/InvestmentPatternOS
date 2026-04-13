# Phase 1 + 2 Optimization Deployment Guide

## Overview
This guide walks through deploying the token cost optimization (Phase 1 + 2) which reduces cost per scan from **$0.10-0.40 USD → <$0.01 USD**.

---

## Prerequisites
- PatternOS backend running
- PostgreSQL database accessible
- Python 3.10+ with dependencies installed

---

## Deployment Steps

### Step 1: Verify Environment Configuration
```bash
cd PatternOS
cat .env | grep LLM_SCREENING_MODEL
```

**Expected output:**
```
LLM_SCREENING_MODEL=google/gemini-2.0-flash-lite
LLM_CHAT_MODEL=google/gemini-2.0-flash-lite
LLM_FALLBACK_MODEL=google/gemini-2.0-flash-lite
```

✓ If correct, skip to Step 2.
✗ If not, update `.env` with the correct models (already done).

---

### Step 2: Initialize Cache Table

Run the schema initialization script to create the ScreeningCache table:

```bash
cd backend
python -m app.db.init_schema
```

**Expected output:**
```
Creating database schema...
✓ Database schema initialized successfully!
```

✓ Success! The `screening_cache` table is now created.
✗ If error, check:
  - PostgreSQL is running
  - DATABASE_URL in .env is correct
  - User has CREATE TABLE permissions

---

### Step 3: Restart Backend Server

If using the development server with hot-reload:
```bash
# Backend should auto-reload with file changes
# Monitor logs for startup message
```

Expected log output on startup:
```
[Cache] Purged 0 expired screening results on startup
[Scheduler] Cache cleanup job registered (runs every 6 hours)
```

If using manual restart:
```bash
# Stop current backend process (Ctrl+C)
# Restart:
python -m uvicorn app.main:app --reload --port 8000
```

---

### Step 4: Verify Cache Operations

Once backend is running, test cache functionality:

```bash
# Option A: Check health endpoint
curl http://localhost:8000/health

# Option B: Run a test scan
curl -X POST http://localhost:8000/api/v1/scan \
  -H "Content-Type: application/json" \
  -d '{"symbols": ["INFY", "TCS", "RELIANCE"]}'
```

Watch backend logs for:
- ✓ First run: No cache hits (expected)
- ✓ Second run: Cache hits appear (2-3 of 3 symbols cached)
- ✓ Log pattern: `Cache hit for INFY | LLM screening unavailable — using base score`

---

### Step 5: Monitor Cost Metrics

#### Real-time Cost Tracking
1. **Monitor OpenRouter API usage:**
   - Visit https://openrouter.ai/account/usage
   - Track tokens per day

2. **Compare baseline:**
   - Day 1 (no cache): 50 LLM calls × 600 tokens = 30,000 tokens
   - Day 2 (with cache): 25 LLM calls × 600 tokens = 15,000 tokens (50% reduction)
   - Day 3+ (with cache): 5-10 LLM calls × 600 tokens = 3,000-6,000 tokens

3. **Cost calculation:**
   - Gemini 2.0 Flash Lite: ~$0.075 per 1M input tokens
   - 30,000 tokens = $0.00225 USD
   - **Expected per scan: <$0.01 USD** ✓

#### View Cache Statistics
```python
# In Python REPL:
from app.db.session import SessionLocal
from app.db.models import ScreeningCache
from datetime import datetime, timedelta

db = SessionLocal()

# Count cached entries
total = db.query(ScreeningCache).count()
active = db.query(ScreeningCache).filter(
    ScreeningCache.cached_at > datetime.utcnow() - timedelta(hours=24)
).count()

print(f"Total cache entries: {total}")
print(f"Active (24h): {active}")

# Check cache hit rate over last day
from sqlalchemy import func
stats = db.query(
    func.count(ScreeningCache.id).label('entries'),
    func.min(ScreeningCache.cached_at).label('oldest'),
    func.max(ScreeningCache.cached_at).label('newest')
).first()

print(f"Cache age: {stats.oldest} → {stats.newest}")
```

---

## Testing

### Test 1: Basic Cache Functionality
```python
from app.cache.signal_cache import (
    get_cached_screening, store_screening_result
)
from app.db.session import SessionLocal

db = SessionLocal()

# Store a test result
store_screening_result(
    pattern_id="test-pattern-id",
    symbol="TEST",
    timeframe="1d",
    base_score=75.0,
    adjusted_score=78.5,
    analysis_text="Test analysis",
    db=db
)

# Retrieve it
result = get_cached_screening(
    pattern_id="test-pattern-id",
    symbol="TEST",
    timeframe="1d",
    db=db
)

if result:
    score, analysis = result
    print(f"✓ Cache works! Score: {score}, Analysis: {analysis}")
else:
    print("✗ Cache retrieval failed")
```

### Test 2: Cache Expiration
```python
from datetime import datetime, timedelta
from app.cache.signal_cache import get_cached_screening
from app.db.models import ScreeningCache

# Simulate expired entry (set cached_at to 25 hours ago)
expired = ScreeningCache(
    pattern_id="expired-test",
    symbol="EXPIRED",
    timeframe="1d",
    base_score=75.0,
    adjusted_score=78.5,
    analysis_text="Will expire",
    cached_at=datetime.utcnow() - timedelta(hours=25)
)
db.add(expired)
db.commit()

# Try to retrieve (should be None)
result = get_cached_screening(
    pattern_id="expired-test",
    symbol="EXPIRED",
    timeframe="1d",
    db=db
)

if result is None:
    print("✓ Expiration works! Expired entry was auto-deleted")
else:
    print("✗ Expiration failed")
```

### Test 3: Performance Improvement
```bash
# Run a full scan and time it
import time
from app.scanner.engine import run_scan
from app.db.session import SessionLocal

db = SessionLocal()

# First run (no cache)
start = time.time()
result1 = await run_scan(db=db, symbols=["INFY", "TCS", "RELIANCE"])
time1 = time.time() - start
print(f"First scan: {time1:.2f}s, {result1['signals_created']} signals")

# Second run (with cache)
start = time.time()
result2 = await run_scan(db=db, symbols=["INFY", "TCS", "RELIANCE"])
time2 = time.time() - start
print(f"Second scan: {time2:.2f}s, {result2['signals_created']} signals")

# Should be 30-50% faster due to cache hits
print(f"Speedup: {time1/time2:.1f}x faster")
```

---

## Troubleshooting

### Issue: "ScreeningCache table does not exist"
**Solution:**
```bash
cd backend
python -m app.db.init_schema
```
Then restart the backend.

### Issue: Cache cleanup job not running
**Solution:**
```python
# Check scheduler status
from app.scheduler.jobs import scheduler
print(f"Scheduler running: {scheduler.running}")
print(f"Jobs: {len(scheduler.get_jobs())}")

# Should show 2 jobs:
# - daily_scan_nse (7 AM IST)
# - cleanup_expired_cache (every 6 hours)
```

### Issue: Cache not appearing in database
**Solution:**
```sql
-- Check if ScreeningCache table exists
SELECT table_name FROM information_schema.tables
WHERE table_name = 'screening_cache';

-- If exists, check content
SELECT COUNT(*) as cache_entries FROM screening_cache;

-- If empty, run a scan to populate:
curl -X POST http://localhost:8000/api/v1/scan \
  -H "Content-Type: application/json" \
  -d '{"symbols": ["INFY"]}'
```

### Issue: High cache miss rate (no improvement)
**Possible causes:**
- Different symbols in each scan (cache misses are expected)
- Cache expired (check timestamps in DB)
- Different timeframes (cache is per-timeframe)

**Solution:**
1. Scan same universe repeatedly: `["INFY", "TCS", "RELIANCE", ...]`
2. Check cache age: Entries older than 24h are auto-deleted
3. Verify all scans use same timeframe (default: "1d")

---

## Rollback Plan

If issues occur, revert to previous state:

```bash
# 1. Disable cache queries in engine.py
#    Comment out lines 44-74 (cache lookup and storage)
#    Restore original LLM call:
#    adjusted_score, analysis = await llm_screen(...)

# 2. Stop scheduler cache cleanup
#    Comment out cleanup_expired_cache() in scheduler/jobs.py

# 3. Keep ScreeningCache table (won't cause issues if unused)
#    Or drop if needed:
#    DROP TABLE screening_cache;

# 4. Restart backend
python -m uvicorn app.main:app --reload --port 8000
```

---

## Performance Metrics

### Expected Results After Deployment

| Metric | Baseline | With Phase 1+2 | Status |
|--------|----------|----------------|--------|
| **Cost per 326-symbol scan** | $0.15-0.40 | $0.001-0.005 | ✓ 99% reduction |
| **LLM calls per scan** | 50 | 15 (with cache) | ✓ 70% reduction |
| **Tokens per call** | 950 | 600 | ✓ 37% reduction |
| **Avg response time** | 45-90s | 20-30s | ✓ 50% faster |
| **Cache hit rate** | N/A | 30-40% | ✓ 30-40% LLM savings |

### Monitoring Query
```sql
-- Track daily cost
SELECT
    DATE_TRUNC('day', cached_at) as day,
    COUNT(*) as cache_entries,
    COUNT(DISTINCT pattern_id) as patterns,
    COUNT(DISTINCT symbol) as symbols
FROM screening_cache
GROUP BY DATE_TRUNC('day', cached_at)
ORDER BY day DESC;
```

---

## Support & Questions

For issues or questions about the optimization:

1. **Check logs:** Backend logs will show cache hits/misses
2. **Verify database:** Confirm ScreeningCache table exists and has entries
3. **Review optimization report:** See `OPTIMIZATION_REPORT.md` for detailed analysis
4. **Monitor costs:** Track OpenRouter API usage to verify cost reduction

---

**Deployment Status:** Ready ✓
**Last Updated:** 2026-04-04
**Estimated Deployment Time:** 5-10 minutes
