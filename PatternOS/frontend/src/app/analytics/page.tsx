"use client";
import { useEffect, useState } from "react";
import { analyticsApi, patternsApi, type PatternStats, type Pattern } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { toast } from "sonner";
import { TrendingUp, Zap } from "lucide-react";

function WinRateBar({ rate }: { rate: number }) {
  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 h-1.5 bg-muted rounded-full overflow-hidden">
        <div
          className={`h-full rounded-full ${rate >= 60 ? "bg-green-500" : rate >= 40 ? "bg-yellow-500" : "bg-red-500"}`}
          style={{ width: `${rate}%` }}
        />
      </div>
      <span className="text-xs font-medium w-10 text-right">{rate.toFixed(0)}%</span>
    </div>
  );
}

export default function AnalyticsPage() {
  const [stats, setStats] = useState<PatternStats[]>([]);
  const [patterns, setPatterns] = useState<Pattern[]>([]);
  const [loading, setLoading] = useState(true);
  const [auditing, setAuditing] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([analyticsApi.patterns(), patternsApi.list()])
      .then(([s, p]) => { setStats(s); setPatterns(p); })
      .finally(() => setLoading(false));
  }, []);

  const runAudit = async (patternId: string, patternName: string) => {
    setAuditing(patternId);
    try {
      const res = await fetch(
        `${process.env.NEXT_PUBLIC_API_BASE_URL}/analytics/audit/${patternId}`,
        { method: "POST" }
      );
      if (!res.ok) throw new Error();
      toast.success(`Audit complete for ${patternName}`);
    } catch {
      toast.error("Audit failed — needs more outcome data");
    } finally {
      setAuditing(null);
    }
  };

  if (loading) return <div className="text-muted-foreground text-sm">Loading analytics...</div>;

  return (
    <div className="space-y-6 max-w-5xl">
      <div>
        <h1 className="text-2xl font-bold">Analytics</h1>
        <p className="text-muted-foreground text-sm">Pattern performance and win rate analysis</p>
      </div>

      {stats.length === 0 ? (
        <div className="text-muted-foreground text-sm py-12 text-center">
          No data yet. Run scans and record outcomes to see analytics.
        </div>
      ) : (
        <div className="space-y-4">
          {stats.map((s) => {
            const pattern = patterns.find((p) => p.id === s.pattern_id);
            return (
              <Card key={s.pattern_id}>
                <CardHeader className="pb-2">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <CardTitle className="text-base">{s.pattern_name}</CardTitle>
                      {pattern && (
                        <Badge variant={pattern.status === "active" ? "default" : "secondary"} className="text-xs">
                          {pattern.status}
                        </Badge>
                      )}
                    </div>
                    <Button
                      size="sm"
                      variant="outline"
                      disabled={auditing === s.pattern_id}
                      onClick={() => runAudit(s.pattern_id, s.pattern_name)}
                    >
                      <Zap className="h-3 w-3 mr-1" />
                      {auditing === s.pattern_id ? "Auditing..." : "LLM Audit"}
                    </Button>
                  </div>
                </CardHeader>
                <CardContent className="space-y-3">
                  <div className="grid grid-cols-5 gap-4 text-center">
                    {[
                      { label: "Signals", value: s.total_signals },
                      { label: "Reviewed", value: s.reviewed },
                      { label: "Executed", value: s.executed },
                      { label: "Hit Target", value: s.hit_target, green: true },
                      { label: "Stopped Out", value: s.stopped_out, red: true },
                    ].map(({ label, value, green, red }) => (
                      <div key={label}>
                        <div className={`text-xl font-bold ${green ? "text-green-400" : red ? "text-red-400" : ""}`}>
                          {value}
                        </div>
                        <div className="text-xs text-muted-foreground">{label}</div>
                      </div>
                    ))}
                  </div>

                  <Separator />

                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <p className="text-xs text-muted-foreground mb-1">Win Rate</p>
                      {s.win_rate !== null ? (
                        <WinRateBar rate={s.win_rate} />
                      ) : (
                        <span className="text-xs text-muted-foreground">No completed trades</span>
                      )}
                    </div>
                    <div>
                      <p className="text-xs text-muted-foreground mb-1">Avg P&L</p>
                      {s.avg_pnl_pct !== null ? (
                        <div className={`flex items-center gap-1 text-sm font-semibold ${s.avg_pnl_pct >= 0 ? "text-green-400" : "text-red-400"}`}>
                          <TrendingUp className="h-3 w-3" />
                          {s.avg_pnl_pct > 0 ? "+" : ""}{s.avg_pnl_pct.toFixed(2)}%
                        </div>
                      ) : (
                        <span className="text-xs text-muted-foreground">—</span>
                      )}
                    </div>
                  </div>
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}
    </div>
  );
}
