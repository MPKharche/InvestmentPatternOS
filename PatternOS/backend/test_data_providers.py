"""Quick sanity test for data providers."""

import sys

print("=== Testing yfinance client ===")
try:
    from app.data.yfinance_client import (
        fetch_stock_prices,
        fetch_stock_info,
        get_stock_fundamentals,
    )

    # Test fetch_stock_prices
    print("Fetching price for RELIANCE.NS...")
    df = fetch_stock_prices("RELIANCE", "1d", 10, "NSE", use_cache=False)
    if df.empty:
        print("WARNING: No price data returned")
    else:
        print(f"Got {len(df)} rows; latest close: {df['Close'].iloc[-1]:.2f}")

    # Test fundamentals
    print("Fetching fundamentals for RELIANCE.NS...")
    f = get_stock_fundamentals("RELIANCE")
    print(
        f"Fundamentals: P/E={f.get('pe_ratio')}, P/B={f.get('pb_ratio')}, ROE={f.get('roe')}"
    )
except Exception as e:
    print(f"ERROR: {e}")
    sys.exit(1)

print("\n=== Testing NSEpy client ===")
try:
    from app.data.nsepy_client import fetch_pcr_data, fetch_nifty_50_oi

    # Test PCR
    print("Fetching PCR for NIFTY...")
    pcr = fetch_pcr_data()
    print(
        f"NIFTY PCR: {pcr.get('pcr')}, CE={pcr.get('total_ce_oi')}, PE={pcr.get('total_pe_oi')}"
    )

    # Test OI history
    print("Fetching NIFTY OI history...")
    df_oi = fetch_nifty_50_oi()
    if df_oi.empty:
        print("WARNING: No OI data returned")
    else:
        print(
            f"Got {len(df_oi)} days of OI data; latest OI: {df_oi['OpenInterest'].iloc[-1]}"
        )
except Exception as e:
    print(f"ERROR: {e}")
    sys.exit(1)

print("\n✅ All data provider tests passed!")
