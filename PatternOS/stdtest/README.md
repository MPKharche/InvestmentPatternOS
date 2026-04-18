# PatternOS Standard Test Runner

Runs a fresh, repeatable “full stack” verification:
- PostgreSQL (docker)
- Backend migrations + deterministic seed
- Backend pytest
- Frontend Playwright E2E

## One command (Windows PowerShell)

```powershell
cd C:\Users\mayur\Downloads\AppDevelopment\InvestmentApp\PatternOS
.\stdtest\run.ps1
```

Artifacts (logs) are written under `stdtest/.artifacts/<timestamp>/`.

## Notes
- Uses `APP_ENV=test`, `LLM_DISABLED=true`, and disables Telegram delivery for offline-safe runs.
- Optional engines (`TA-Lib`, `vectorbt`) are detected automatically; E2E adapts where needed.

