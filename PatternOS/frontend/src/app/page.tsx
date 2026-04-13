"use client";
import { useEffect, useState } from "react";
import { analyticsApi, type AnalyticsSummary } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { BarChart3, CheckCircle2, Radio, TrendingUp, XCircle, Zap } from "lucide-react";

function StatCard({
  title, value, icon: Icon, sub, variant = "default",
}: {
  title: string; value: string | number; icon: React.ElementType; sub?: string; variant?: "default" | "green" | "red";
}) {
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between pb-2">
        <CardTitle className="text-sm font-medium text-muted-foreground">{title}</CardTitle>
        <Icon className="h-4 w-4 text-muted-foreground" />
      </CardHeader>
      <CardContent>
        <div className={`text-2xl font-bold ${variant === "green" ? "text-green-400" : variant === "red" ? "text-red-400" : ""}`}>
          {value}
        </div>
        {sub && <p className="text-xs text-muted-foreground mt-1">{sub}</p>}
      </CardContent>
    </Card>
  );
}

export default function DashboardPage() {
  const [summary, setSummary] = useState<AnalyticsSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  useEffect(() => {
    analyticsApi.summary()
      .then(setSummary)
      .catch(() => setError(true))
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return <div className="text-muted-foreground text-sm">Loading dashboard...</div>;
  }

  if (error || !summary) {
    return <div className="text-destructive text-sm">Failed to load. Is the backend running at localhost:8000?</div>;
  }

  return (
    <div className="space-y-6 max-w-5xl">
      <div>
        <h1 className="text-2xl font-bold">Dashboard</h1>
        <p className="text-muted-foreground text-sm mt-1">PatternOS signal intelligence overview</p>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
        <StatCard
          title="Pending Review"
          value={summary.pending_review}
          icon={Radio}
          sub="High-confidence signals awaiting you"
          variant={summary.pending_review > 0 ? "green" : "default"}
        />
        <StatCard title="Active Patterns" value={summary.active_patterns} icon={Zap} sub="Scanning the universe" />
        <StatCard title="Total Signals" value={summary.total_signals} icon={BarChart3} sub="All time" />
        <StatCard title="Executed Trades" value={summary.executed_trades} icon={TrendingUp} />
        <StatCard title="Hit Target" value={summary.hit_target} icon={CheckCircle2} variant="green" />
        <StatCard title="Stopped Out" value={summary.stopped_out} icon={XCircle} variant="red" />
      </div>

      {summary.overall_win_rate !== null && (
        <Card>
          <CardHeader>
            <CardTitle className="text-sm">Overall Win Rate</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex items-center gap-3">
              <div className="text-3xl font-bold text-green-400">{summary.overall_win_rate}%</div>
              <Badge variant={summary.overall_win_rate >= 50 ? "default" : "destructive"}>
                {summary.overall_win_rate >= 50 ? "Positive Edge" : "Needs Review"}
              </Badge>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
