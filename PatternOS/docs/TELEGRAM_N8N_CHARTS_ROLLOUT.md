# Telegram, n8n, and chart consistency — implementation rollout

**Status:** Implemented on branch `dev` — scheduler fix, `N8N_WEBHOOK_*` + `app/integrations/events.py`, chart theme (`frontend/src/lib/chart-theme.ts`), status UI, tests.

Historical notes below document behaviour and manual n8n setup.

## 1. Telegram — current state

**Already implemented:**

- [`backend/app/alerts/telegram.py`](../backend/app/alerts/telegram.py): outbox + `sendPhoto`/`sendMessage`, chart PNG via `render_equity_chart_png`, inline buttons → `TelegramFeedback`.
- [`backend/app/telegram/worker.py`](../backend/app/telegram/worker.py): polling bot (`/chart`, `/signal`, `/mf`, `/mfchart`, callbacks). Requires `python-telegram-bot` (listed in `requirements.txt`).
- Env: [`PatternOS/.env.example`](../.env.example): `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `TELEGRAM_MODE=disabled|polling`, `TELEGRAM_ALERTS_ENABLED`.

**Critical bug (must fix):** In [`backend/app/scheduler/jobs.py`](../backend/app/scheduler/jobs.py), `daily_scan_nse` **returns early** when `TELEGRAM_MODE == polling`. That disables the **main API server’s daily scan** whenever you run the separate polling worker with `TELEGRAM_MODE=polling`. The worker and API should **both** run: polling is a **separate process**, not a reason to skip NSE scanning.

**Fix:** Remove this guard from `daily_scan_nse` (or replace with a dedicated opt-out env such as `DISABLE_SCHEDULED_SCAN=true` only if you truly want no cron scan):

```python
# REMOVE:
if settings.TELEGRAM_MODE.strip().lower() == "polling":
    return
```

**Runtime topology:**

1. Start PostgreSQL + PatternOS API (`uvicorn` / `dev-up`).
2. Set `.env`: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `TELEGRAM_ALERTS_ENABLED=true`, `TELEGRAM_MODE=polling` **only on the worker process** OR use the same `.env` for both **after** removing the scheduler guard above.
3. Second terminal: `cd PatternOS/backend && python -m app.telegram.worker`

Until the guard is removed, **never** set `TELEGRAM_MODE=polling` on the API server if you rely on scheduled scans.

---

## 2. n8n at `http://localhost:5678/`

**Purpose:** Optional **fan-out** for events (Slack, email, logging) without putting that logic in PatternOS.

**Add config** (`app/config.py` + `.env.example`):

```python
N8N_WEBHOOK_URL: str = ""       # e.g. http://localhost:5678/webhook/patternos-events
N8N_WEBHOOK_SECRET: str = ""    # optional; sent as X-PatternOS-Secret
```

**Add module** `backend/app/integrations/events.py`:

- `emit_patternos_event_sync(event_type, payload)` — `httpx.post`, 8s timeout, swallow errors.
- `emit_patternos_event(...)` — async variant for `scanner/engine.py`.

**Call sites:**

- After equity signal is persisted in [`scanner/engine.py`](../backend/app/scanner/engine.py) (after `enqueue_telegram_alert`), emit e.g.  
  `equity_signal_created` with `{ "symbol", "pattern_id", "pattern_name", "confidence", "timeframe" }`.
- In [`mf/pipelines.py`](../backend/app/mf/pipelines.py) inside `generate_nav_signals`, after `db.commit()`, if `created > 0`, emit  
  `mf_signals_created` with `{ "scheme_code", "nav_date", "created" }`.

**Extend** [`api/routes/meta.py`](../backend/app/api/routes/meta.py) `capabilities` with  
`n8n_webhook_configured: bool(settings.N8N_WEBHOOK_URL.strip())`.

**n8n workflow (manual):**

1. New workflow → **Webhook** node, POST, path `patternos-events`, **Production URL** copy into `N8N_WEBHOOK_URL`.
2. Optional: **IF** on `$json.event` equals `equity_signal_created` vs `mf_signals_created`.
3. **Telegram** / **Slack** / **Email** nodes as needed.

---

## 3. Chart UI consistency

**Canonical theme (equity Chart Tool):** [`frontend/src/app/chart/page.tsx`](../frontend/src/app/chart/page.tsx) uses `BG = "#0a0a0c"`, `GRID = "#111115"`, `CHART_OPTS` + `CrosshairMode`.

**Inconsistencies:**

- [`chart-widget.tsx`](../frontend/src/components/chart-widget.tsx) uses background `#0f0f11`.
- MF pages ([`mf/chart/page.tsx`](../frontend/src/app/mf/chart/page.tsx), [`mf/schemes/[scheme_code]/page.tsx`](../frontend/src/app/mf/schemes/[scheme_code]/page.tsx)) use **transparent** background and lighter grid — intentional for cards, but **candle colors** and **crosshair** should match.

**Add** `frontend/src/lib/chart-theme.ts`:

- Export `PATTERN_OS_BG`, `PATTERN_OS_GRID`, `patternOsChartMainOptions` (same as current `CHART_OPTS`), `patternOsCandlestickSeriesDefaults`, `patternOsChartMfCardOptions` (transparent BG + same grid/crosshair as main where possible).

**Refactor:** Import these in `chart/page.tsx`, `chart-widget.tsx`, and MF chart pages; remove duplicated literals.

---

## 4. Pattern “deployment” consistency (equity vs MF)

| Asset | “Live” means | Where |
|--------|----------------|--------|
| Equity | `patterns.status == "active"` | Scanner loads only active patterns |
| MF | `mf_rulebooks.status == "active"` | `pipelines._active_rulebook` |

**No code change required** for parity — both are **active rulebook in DB**. Optional UX: add a one-line note on **Studio** and **MF Rulebooks** pages: “Only **active** patterns/rulebooks participate in automated scans.”

---

## 5. Verification

```powershell
cd InvestmentApp\PatternOS\backend
pytest -q --tb=no -x
```

```powershell
cd InvestmentApp\PatternOS\frontend
npm run build
```

---

## 6. Optional scripts

- `PatternOS/run-telegram-worker.bat`: `cd backend && python -m app.telegram.worker`
