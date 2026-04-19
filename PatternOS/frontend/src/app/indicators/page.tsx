"use client";
import { useState, useEffect, useCallback } from "react";
import { dataApi, type StockIndicatorsResponse } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { IndicatorCharts } from "@/components/indicator-charts";
import { toast } from "sonner";
import { Loader2 } from "lucide-react";

export default function IndicatorsPage() {
  // Form state
  const [symbol, setSymbol] = useState("RELIANCE.NS");
  const [timeframe, setTimeframe] = useState("1d");
  const [days, setDays] = useState(120);
  const [exchange, setExchange] = useState("NSE");

  // Indicator toggles & params
  const [showSMA, setShowSMA] = useState(true);
  const [showEMA, setShowEMA] = useState(false);
  const [showBB, setShowBB] = useState(false);
  const [showRSI, setShowRSI] = useState(false);
  const [showMACD, setShowMACD] = useState(false);
  const [showATR, setShowATR] = useState(false);

  const [rsiPeriod, setRsiPeriod] = useState(14);
  const [smaPeriods, setSmaPeriods] = useState("20,50,200");
  const [macdFast, setMacdFast] = useState(12);
  const [macdSlow, setMacdSlow] = useState(26);
  const [macdSignal, setMacdSignal] = useState(9);
  const [bbWindow, setBbWindow] = useState(20);
  const [bbStd, setBbStd] = useState(2.0);
  const [atrPeriod, setAtrPeriod] = useState(14);

  const [data, setData] = useState<StockIndicatorsResponse | null>(null);
  const [loading, setLoading] = useState(false);

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const indicatorsParam = "all"; // we compute all always, easier
      const result = await dataApi.getStockIndicators(symbol, {
        timeframe,
        days,
        exchange,
        indicators: indicatorsParam,
        rsiPeriod,
        smaPeriods,
        macdFast,
        macdSlow,
        macdSignal,
        bbWindow,
        bbStd,
        atrPeriod,
      });
      setData(result);
    } catch (e) {
      toast.error("Failed to fetch indicators");
      console.error(e);
    } finally {
      setLoading(false);
    }
  }, [symbol, timeframe, days, exchange, showRSI, showMACD, showATR, showSMA, showEMA, showBB, rsiPeriod, smaPeriods, macdFast, macdSlow, macdSignal, bbWindow, bbStd, atrPeriod]);

  // Auto-load on first mount? Optional: load with defaults
  useEffect(() => {
    loadData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [symbol, timeframe, days]); // Other params changes require manual "Load" button

  const handleLoad = () => {
    loadData();
  };

  return (
    <div className="space-y-6 max-w-6xl">
      <div>
        <h1 className="text-2xl font-bold">Indicator Playground</h1>
        <p className="text-muted-foreground text-sm">Adjust parameters and visualize technical indicators.</p>
      </div>

      {/* Controls */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Data Source</CardTitle>
        </CardHeader>
        <CardContent className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div className="space-y-1">
            <Label htmlFor="symbol">Symbol</Label>
            <Input id="symbol" value={symbol} onChange={(e) => setSymbol(e.target.value)} placeholder="RELIANCE.NS" />
          </div>
          <div className="space-y-1">
            <Label htmlFor="timeframe">Timeframe</Label>
            <select id="timeframe" value={timeframe} onChange={(e) => setTimeframe(e.target.value)} className="w-full h-9 rounded border border-border bg-muted px-2 text-xs">
              <option value="1d">1d</option>
              <option value="1h">1h</option>
              <option value="1w">1w</option>
              <option value="1mo">1mo</option>
            </select>
          </div>
          <div className="space-y-1">
            <Label htmlFor="days">Days</Label>
            <Input id="days" type="number" value={days} onChange={(e) => setDays(Number(e.target.value))} min={10} max={2000} />
          </div>
          <div className="space-y-1">
            <Label htmlFor="exchange">Exchange</Label>
            <select id="exchange" value={exchange} onChange={(e) => setExchange(e.target.value)} className="w-full h-9 rounded border border-border bg-muted px-2 text-xs">
              <option value="NSE">NSE</option>
              <option value="BSE">BSE</option>
              <option value="NASDAQ">NASDAQ</option>
              <option value="NYSE">NYSE</option>
            </select>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Indicators</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex flex-wrap gap-4">
            {[
              { key: "sma", label: "SMA", checked: showSMA },
              { key: "ema", label: "EMA", checked: showEMA },
              { key: "bb", label: "Bollinger Bands", checked: showBB },
              { key: "rsi", label: "RSI", checked: showRSI },
              { key: "macd", label: "MACD", checked: showMACD },
              { key: "atr", label: "ATR", checked: showATR },
            ].map((item) => (
              <label key={item.key} className="flex items-center gap-2 text-xs">
                <input
                  type="checkbox"
                  checked={item.checked}
                  onChange={(e) => {
                    switch (item.key) {
                      case "sma": setShowSMA(e.target.checked); break;
                      case "ema": setShowEMA(e.target.checked); break;
                      case "bb": setShowBB(e.target.checked); break;
                      case "rsi": setShowRSI(e.target.checked); break;
                      case "macd": setShowMACD(e.target.checked); break;
                      case "atr": setShowATR(e.target.checked); break;
                    }
                  }}
                />
                {item.label}
              </label>
            ))}
          </div>

          {/* Parameter inputs */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-xs">
            {showRSI && (
              <div className="space-y-1">
                <Label>RSI Period</Label>
                <Input type="number" value={rsiPeriod} onChange={(e) => setRsiPeriod(Number(e.target.value))} min={2} max={50} />
              </div>
            )}
            {showSMA && (
              <div className="space-y-1">
                <Label>SMA Periods (comma)</Label>
                <Input value={smaPeriods} onChange={(e) => setSmaPeriods(e.target.value)} placeholder="20,50,200" />
              </div>
            )}
            {showMACD && (
              <>
                <div className="space-y-1">
                  <Label>MACD Fast</Label>
                  <Input type="number" value={macdFast} onChange={(e) => setMacdFast(Number(e.target.value))} min={2} max={50} />
                </div>
                <div className="space-y-1">
                  <Label>MACD Slow</Label>
                  <Input type="number" value={macdSlow} onChange={(e) => setMacdSlow(Number(e.target.value))} min={2} max={50} />
                </div>
                <div className="space-y-1">
                  <Label>MACD Signal</Label>
                  <Input type="number" value={macdSignal} onChange={(e) => setMacdSignal(Number(e.target.value))} min={2} max={50} />
                </div>
              </>
            )}
            {showBB && (
              <>
                <div className="space-y-1">
                  <Label>BB Window</Label>
                  <Input type="number" value={bbWindow} onChange={(e) => setBbWindow(Number(e.target.value))} min={2} max={50} />
                </div>
                <div className="space-y-1">
                  <Label>BB Std Dev</Label>
                  <Input type="number" step="0.1" value={bbStd} onChange={(e) => setBbStd(Number(e.target.value))} min={0.1} max={5} />
                </div>
              </>
            )}
            {showATR && (
              <div className="space-y-1">
                <Label>ATR Period</Label>
                <Input type="number" value={atrPeriod} onChange={(e) => setAtrPeriod(Number(e.target.value))} min={2} max={50} />
              </div>
            )}
          </div>

          <Button onClick={handleLoad} disabled={loading}>
            {loading ? <Loader2 className="h-4 w-4 mr-2 animate-spin" /> : null}
            Load Chart
          </Button>
        </CardContent>
      </Card>

      {/* Charts */}
      {loading && (
        <div className="flex items-center justify-center py-12">
          <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
        </div>
      )}

      {!loading && data && (
        <div className="space-y-4">
          <div className="text-xs text-muted-foreground">
            Showing {data.prices.length} bars for {data.symbol} ({data.timeframe})
            {data.indicators && Object.keys(data.indicators).length > 0 && (
              <span className="ml-2">Indicators: {Object.keys(data.indicators).join(", ")}</span>
            )}
          </div>
          <IndicatorCharts
            prices={data.prices}
            indicators={data.indicators}
            showSMA={showSMA}
            showEMA={showEMA}
            showBB={showBB}
            showRSI={showRSI}
            showMACD={showMACD}
            showATR={showATR}
          />
        </div>
      )}
    </div>
  );
}
