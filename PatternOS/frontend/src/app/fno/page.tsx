"use client";
import { useEffect, useState } from "react";
import { fnoApi, dataApi } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { toast } from "sonner";
import { TrendingUp, TrendingDown, BarChart3, Activity } from "lucide-react";

export default function FnoAnalysisPage() {
  const [symbol, setSymbol] = useState("NIFTY");
  const [pcrData, setPcrData] = useState<any>(null);
  const [oiBuildup, setOiBuildup] = useState<any>(null);
  const [loading, setLoading] = useState(false);

  const loadPCR = async () => {
    setLoading(true);
    try {
      const res = await fnoApi.pcr(symbol === "NIFTY" ? undefined : symbol);
      setPcrData(res);
    } catch (e) {
      toast.error("Failed to load PCR");
    } finally {
      setLoading(false);
    }
  };

  const loadOiBuildup = async () => {
    if (symbol === "NIFTY") return;
    setLoading(true);
    try {
      const res = await fnoApi.oiBuildup(symbol);
      setOiBuildup(res);
    } catch (e) {
      toast.error("Failed to load OI buildup");
    } finally {
      setLoading(false);
    }
  };

  const handleSymbolChange = (val: string) => {
    setSymbol(val.toUpperCase());
    setPcrData(null);
    setOiBuildup(null);
  };

  useEffect(() => {
    loadPCR();
    if (symbol !== "NIFTY") {
      loadOiBuildup();
    }
  }, [symbol]);

  const getPCRInterpretation = (pcr: number | null) => {
    if (pcr === null) return "N/A";
    if (pcr > 1.2) return "Very Bullish (high put writing)";
    if (pcr > 1.0) return "Bullish";
    if (pcr < 0.8) return "Very Bearish (high call buying)";
    if (pcr < 1.0) return "Bearish";
    return "Neutral";
  };

  return (
    <div className="space-y-6 max-w-5xl">
      <div>
        <h1 className="text-2xl font-bold">F&O Analysis</h1>
        <p className="text-muted-foreground text-sm">Put-Call Ratio & Open Interest analysis</p>
      </div>

      <div className="flex items-center gap-3">
        <Input
          placeholder="Symbol (e.g., NIFTY, RELIANCE)"
          value={symbol}
          onChange={e => handleSymbolChange(e.target.value)}
          className="max-w-xs"
        />
        <Button onClick={loadPCR} disabled={loading}>
          <Activity className="h-4 w-4 mr-1" />
          Refresh
        </Button>
      </div>

      {/* PCR Card */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <BarChart3 className="h-5 w-5" />
            Put-Call Ratio
          </CardTitle>
        </CardHeader>
        <CardContent>
          {pcrData ? (
            <div className="grid grid-cols-2 md:grid-cols-4 gap-6">
              <div>
                <div className="text-xs text-muted-foreground">PCR</div>
                <div className={`text-2xl font-bold ${pcrData.pcr != null ? (pcrData.pcr > 1 ? "text-green-500" : "text-red-500") : "text-muted"}`}>
                  {pcrData.pcr != null ? pcrData.pcr.toFixed(2) : "N/A"}
                </div>
                <div className="text-xs text-muted-foreground mt-1">
                  {getPCRInterpretation(pcrData.pcr)}
                </div>
              </div>
              <div>
                <div className="text-xs text-muted-foreground">Total CE OI</div>
                <div className="text-xl font-mono">{pcrData.total_ce_oi.toLocaleString()}</div>
              </div>
              <div>
                <div className="text-xs text-muted-foreground">Total PE OI</div>
                <div className="text-xl font-mono">{pcrData.total_pe_oi.toLocaleString()}</div>
              </div>
              <div>
                <div className="text-xs text-muted-foreground">Sentiment</div>
                <div className={`text-lg font-bold ${pcrData.pcr != null && pcrData.pcr > 1 ? "text-green-500" : "text-red-500"}`}>
                  {pcrData.pcr != null && pcrData.pcr > 1 ? "BULLISH" : "BEARISH"}
                </div>
              </div>
            </div>
          ) : (
            <div className="text-muted-foreground">Loading PCR data...</div>
          )}
        </CardContent>
      </Card>

      {/* OI Buildup Card (only for stocks) */}
      {symbol !== "NIFTY" && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Activity className="h-5 w-5" />
              Open Interest Buildup — {symbol}
            </CardTitle>
          </CardHeader>
          <CardContent>
            {oiBuildup ? (
              <div className="space-y-4">
                <div className="grid grid-cols-3 gap-4">
                  <div>
                    <div className="text-xs text-muted-foreground">Expiry</div>
                    <div className="font-mono text-sm">{oiBuildup.expiry}</div>
                  </div>
                  <div>
                    <div className="text-xs text-muted-foreground">Total CE OI</div>
                    <div className="font-mono">{oiBuildup.total_ce_oi.toLocaleString()}</div>
                  </div>
                  <div>
                    <div className="text-xs text-muted-foreground">Total PE OI</div>
                    <div className="font-mono">{oiBuildup.total_pe_oi.toLocaleString()}</div>
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-6">
                  <div>
                    <h4 className="text-sm font-semibold mb-2">Top Call Strikes (by OI)</h4>
                    <div className="space-y-1">
                      {oiBuildup.top_call_strikes.map((c: any, i: number) => (
                        <div key={i} className="flex justify-between text-sm border-b border-muted pb-1">
                          <span className="font-mono">Strike {c.strike}</span>
                          <span className="text-muted-foreground">OI: {c.openInterest?.toLocaleString()}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                  <div>
                    <h4 className="text-sm font-semibold mb-2">Top Put Strikes (by OI)</h4>
                    <div className="space-y-1">
                      {oiBuildup.top_put_strikes.map((p: any, i: number) => (
                        <div key={i} className="flex justify-between text-sm border-b border-muted pb-1">
                          <span className="font-mono">Strike {p.strike}</span>
                          <span className="text-muted-foreground">OI: {p.openInterest?.toLocaleString()}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              </div>
            ) : (
              <div className="text-muted-foreground">Loading OI buildup...</div>
            )}
          </CardContent>
        </Card>
      )}

      {symbol === "NIFTY" && (
        <Card>
          <CardHeader>
            <CardTitle>NIFTY Futures OI History</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-sm text-muted-foreground">
              OI history chart placeholder. Use NIFTY OI data to see institutional money flow trends.
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
