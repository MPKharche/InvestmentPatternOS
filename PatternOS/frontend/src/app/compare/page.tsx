"use client";
import { useEffect, useState } from "react";
import { compareApi, type ComparisonItem } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";
import { BarChart3, TrendingUp, TrendingDown } from "lucide-react";

export default function StockComparisonPage() {
  const [symbolsInput, setSymbolsInput] = useState("RELIANCE, TCS, INFY");
  const [comparisons, setComparisons] = useState<ComparisonItem[]>([]);
  const [loading, setLoading] = useState(false);

  const load = async () => {
    const symbols = symbolsInput.split(",").map(s => s.trim()).filter(Boolean).join(",");
    if (!symbols) return;
    setLoading(true);
    try {
      const res = await compareApi.stocks(symbols, "NSE");
      setComparisons(res.comparisons);
    } catch (e) {
      toast.error("Failed to compare stocks");
    } finally {
      setLoading(false);
    }
  };

  const formatFundamental = (label: string, value: number | null | undefined, suffix = "") => (
    <div key={label} className="flex justify-between text-sm border-b border-muted last:border-0">
      <span className="text-muted-foreground">{label}</span>
      <span className="font-mono">{value != null ? value.toFixed(2) + suffix : "—"}</span>
    </div>
  );

  return (
    <div className="space-y-6 max-w-6xl">
      <div>
        <h1 className="text-2xl font-bold">Stock Comparison</h1>
        <p className="text-muted-foreground text-sm">Compare fundamentals & technicals side-by-side</p>
      </div>

      <div className="flex items-center gap-3">
        <Input
          placeholder="Enter symbols, comma-separated (max 5)"
          value={symbolsInput}
          onChange={e => setSymbolsInput(e.target.value.toUpperCase())}
          className="max-w-md"
        />
        <Button onClick={load} disabled={loading}>
          <BarChart3 className="h-4 w-4 mr-1" />
          {loading ? "Comparing..." : "Compare"}
        </Button>
      </div>

      {comparisons.length === 0 && !loading ? (
        <div className="text-muted-foreground text-sm py-12 text-center">
          Enter symbols to see comparison.
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-6">
          {comparisons.map((c) => (
            <Card key={c.symbol}>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <span className="text-lg font-bold">{c.symbol}</span>
                  {c.technicals.price && (
                    <Badge variant="outline" className="ml-auto">
                      ₹{c.technicals.price.toFixed(2)}
                    </Badge>
                  )}
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-6">
                {/* Fundamentals */}
                <div>
                  <h3 className="text-xs font-semibold uppercase text-muted-foreground mb-2">Fundamentals</h3>
                  <div className="space-y-1">
                    {formatFundamental("P/E", c.fundamentals.pe_ratio)}
                    {formatFundamental("P/B", c.fundamentals.pb_ratio)}
                    {formatFundamental("Debt/Equity", c.fundamentals.debt_to_equity)}
                    {formatFundamental("ROE %", c.fundamentals.roe, "%")}
                    {formatFundamental("Div Yield %", c.fundamentals.dividend_yield, "%")}
                    {formatFundamental("Beta", c.fundamentals.beta)}
                    {formatFundamental("Market Cap", c.fundamentals.market_cap ? c.fundamentals.market_cap / 1e9 : null, "B")}
                  </div>
                </div>

                {/* Technicals */}
                <div>
                  <h3 className="text-xs font-semibold uppercase text-muted-foreground mb-2">Technicals (Daily)</h3>
                  <div className="space-y-1">
                    {formatFundamental("SMA 20", c.technicals.sma20)}
                    {formatFundamental("SMA 50", c.technicals.sma50)}
                    {formatFundamental("RSI (14)", c.technicals.rsi_14)}
                    <div className="flex justify-between text-sm">
                      <span className="text-muted-foreground">Price vs SMA20</span>
                      <span className={c.technicals.above_sma20 ? "text-green-500" : "text-red-500"}>
                        {c.technicals.above_sma20 ? "Above" : "Below"}
                      </span>
                    </div>
                    <div className="flex justify-between text-sm">
                      <span className="text-muted-foreground">Price vs SMA50</span>
                      <span className={c.technicals.above_sma50 ? "text-green-500" : "text-red-500"}>
                        {c.technicals.above_sma50 ? "Above" : "Below"}
                      </span>
                    </div>
                    <div className="flex justify-between text-sm border-t border-muted pt-1 mt-1">
                      <span className="text-muted-foreground">MACD</span>
                      <span className={`font-mono ${(c.technicals.macd?.macd || 0) > (c.technicals.macd?.signal || 0) ? "text-green-500" : "text-red-500"}`}>
                        {c.technicals.macd?.macd?.toFixed(4) ?? "—"}
                      </span>
                    </div>
                  </div>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
