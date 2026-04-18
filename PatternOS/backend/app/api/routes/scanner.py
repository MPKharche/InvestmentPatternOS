from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.api.schemas import ScanRequest, ScanResult
from app.scanner.engine import run_scan
from app.scanner.data import fetch_ohlcv
from app.scanner.indicators import compute_indicators, indicators_to_records
from app.scanner.pattern_detector import detect_chart_patterns, detect_candlestick_patterns
from app.scanner.talib_candles import detect_talib_candlestick_patterns

router = APIRouter(prefix="/scanner", tags=["scanner"])


@router.post("/run", response_model=ScanResult)
async def trigger_scan(body: ScanRequest, db: Session = Depends(get_db)):
    """Manually trigger a scan run. Returns results synchronously."""
    return await run_scan(
        db=db,
        pattern_id=body.pattern_id,
        symbols=body.symbols,
        scope=body.scope or "nifty50",
    )


@router.get("/ohlcv")
def get_ohlcv(
    symbol: str = Query(...),
    timeframe: str = Query("1d"),
):
    """
    Proxy OHLCV data from yfinance for the frontend chart widget.
    Returns list of {time, open, high, low, close} dicts.
    """
    df = fetch_ohlcv(symbol, timeframe)
    if df is None:
        return []
    df = df.reset_index()
    # Convert index (Datetime) to string date
    records = []
    for _, row in df.iterrows():
        date_str = str(row.get("Date") or row.get("Datetime") or row.name)[:10]
        rec = {
            "time":  date_str,
            "open":  round(float(row["Open"]),  2),
            "high":  round(float(row["High"]),  2),
            "low":   round(float(row["Low"]),   2),
            "close": round(float(row["Close"]), 2),
        }
        if "Volume" in row and row["Volume"] is not None:
            rec["volume"] = int(row["Volume"])
        records.append(rec)
    return records


@router.get("/indicators")
def get_indicators(
    symbol: str = Query(...),
    timeframe: str = Query("1d"),
):
    """
    Returns per-bar indicator values (EMA, BB, RSI, MACD, ATR, Stochastic, ADX, OBV)
    for the given symbol / timeframe. Frontend uses this to overlay on the chart.
    """
    df = fetch_ohlcv(symbol, timeframe, extended=True)
    if df is None or df.empty:
        return []
    idf = compute_indicators(df)
    return indicators_to_records(idf)


@router.get("/chart-patterns")
def get_chart_patterns(
    symbol: str = Query(...),
    timeframe: str = Query("1d"),
    lookback: int = Query(120, ge=30, le=500),
):
    """
    Detects chart patterns (H&S, double top/bottom, triangles, flags, wedges)
    and candlestick patterns in the last *lookback* bars.
    """
    df = fetch_ohlcv(symbol, timeframe, extended=True)
    if df is None or df.empty:
        return {"chart_patterns": [], "candlestick_patterns": [], "talib_candlestick_patterns": []}
    return {
        "chart_patterns":       detect_chart_patterns(df, lookback=lookback),
        "candlestick_patterns": detect_candlestick_patterns(df, lookback=30),
        "talib_candlestick_patterns": detect_talib_candlestick_patterns(df, lookback=30),
    }
