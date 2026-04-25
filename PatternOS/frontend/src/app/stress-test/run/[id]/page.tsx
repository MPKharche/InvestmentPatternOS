"use client";
import { useEffect, useState } from "react";
import { stressTestApi, type StressTestResult } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Play, RefreshCw, CheckCircle2, XCircle, Loader2 } from "lucide-react";
import { useParams, useRouter } from "next/navigation";
import { toast } from "sonner";

export default function StressTestRunDetailPage() {
  const params = useParams();
  const runId = params.id as string;
  const router = useRouter();

  const [run, setRun] = useState<StressTestResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  useEffect(() => {
    loadRun();
    // Poll for completion if still running
    const interval = setInterval(() => {
      if (run?.status === "running" || run?.status === "queued") {
        loadRun();
      }
    }, 5000); // Poll every 5 seconds
    return () => clearInterval(interval);
  }, [runId, run]);

  const loadRun = async () => {
    setLoading(true);
    try {
      const data = await stressTestApi.getStressTestRun(runId);
      setRun(data);
    } catch {
      toast.error("Failed to load stress test run");
    } finally {
      setLoading(false);
    }
  };

  const handleRefresh = async () => {
    setRefreshing(true);
    try {
      await stressTestApi.getStressTestRun(runId);
      toast.success("Refreshed!");
    } catch {
      toast.error("Failed to refresh");
    } finally {
      setRefreshing(false);
    }
  };

  const handleBackToPortfolio = () => {
    if (run) {
      router.push(`/stress-test/portfolio/${run.portfolio_id}`);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="text-muted-foreground">Loading stress test results...</div>
      </div>
    );
  }

  if (!run) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="text-muted-foreground">Stress test run not found</div>
      </div>
    );
  }

  const formatDate = (dateStr: string | null) => {
    if (!dateStr) return "—";
    return new Date(dateStr).toLocaleString();
  };

  const formatNumber = (num: number | null) => {
    if (num === null) return "—";
    return num.toLocaleString(undefined, { maximumFractionDigits: 2 });
  };

  const formatPercent = (num: number | null) => {
    if (num === null) return "—";
    return `${num >= 0 ? "+" : ""}${num.toFixed(2)}%`;
  };

  const pnlClass =
    run.final_value !== null && run.initial_value !== null
      ? run.final_value > run.initial_value
        ? "text-green-600"
        : run.final_value < run.initial_value
          ? "text-red-600"
          : ""
      : "";

  const returnClass =
    run.final_value !== null && run.initial_value !== null && run.initial_value !== 0
      ? run.final_value > run.initial_value
        ? "text-green-600"
        : "text-red-600"
      : "";

  return (
    <div className="space-y-6 max-w-6xl">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Stress Test Results</h1>
        <div className="flex gap-2">
          <Button
            variant="outline"
            onClick={handleBackToPortfolio}
          >
            ← Back to Portfolio
          </Button>
          <Button
            variant="outline"
            onClick={handleRefresh}
            disabled={refreshing}
          >
            {refreshing ? <Loader2 className="h-4 w-4 mr-2 animate-spin" /> : <RefreshCw className="h-4 w-4 mr-2" />}
            Refresh
          </Button>
        </div>
      </div>

      {/* Run Info */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Run Information</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <p className="text-sm font-medium text-muted-foreground">Scenario</p>
              <p className="text-base">{run.scenario}</p>
            </div>
            <div>
              <p className="text-sm font-medium text-muted-foreground">Period</p>
              <p className="text-base">
                {formatDate(run.start_date)} to {formatDate(run.end_date)}
              </p>
            </div>
            <div>
              <p className="text-sm font-medium text-muted-foreground">Status</p>
              <p
                className={`text-base ${
                  run.status === "completed"
                    ? "text-green-600"
                    : run.status === "failed"
                      ? "text-red-600"
                      : run.status === "running"
                        ? "text-yellow-600"
                        : run.status === "queued"
                          ? "text-blue-600"
                          : ""
                }`}
              >
                {run.status}
              </p>
            </div>
            <div>
              <p className="text-sm font-medium text-muted-foreground">Triggered</p>
              <p className="text-base">{formatDate(run.triggered_at)}</p>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Results Summary */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Results Summary</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <p className="text-sm font-medium text-muted-foreground">Initial Value</p>
              <p className="text-base text-right">{formatNumber(run.initial_value)}</p>
            </div>
            <div>
              <p className="text-sm font-medium text-muted-foreground">Final Value</p>
              <p className="text-base text-right">{formatNumber(run.final_value)}</p>
            </div>
            <div>
              <p className="text-sm font-medium text-muted-foreground">Absolute P&L</p>
              <p className={`text-base text-right ${pnlClass}`}>
                {run.final_value !== null && run.initial_value !== null
                  ? formatNumber(run.final_value - run.initial_value)
                  : "—"}
              </p>
            </div>
            <div>
              <p className="text-sm font-medium text-muted-foreground">Return %</p>
              <p className={`text-base text-right ${pnlClass}`}>
                {run.final_value !== null && run.initial_value !== null && run.initial_value !== 0
                  ? formatPercent(((run.final_value - run.initial_value) / run.initial_value) * 100)
                  : "—"}
              </p>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4 mt-4">
            <div>
              <p className="text-sm font-medium text-muted-foreground">Max Drawdown</p>
              <p className="text-base text-right">{formatPercent(run.max_drawdown_pct)}</p>
            </div>
            <div>
              <p className="text-sm font-medium text-muted-foreground">VaR (95%)</p>
              <p className="text-base text-right">{formatPercent(run.var_95)}</p>
            </div>
            <div>
              <p className="text-sm font-medium text-muted-foreground">Beta Weighted</p>
              <p className="text-base text-right">{formatNumber(run.beta_weighted)}</p>
            </div>
            <div>
              <p className="text-sm font-medium text-muted-foreground">Completed</p>
              <p className="text-base">{formatDate(run.completed_at)}</p>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Per-Symbol Breakdown */}
      {run.results_json && Object.keys(run.results_json).length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Per-Symbol Breakdown</CardTitle>
          </CardHeader>
          <CardContent>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Symbol</TableHead>
                  <TableHead>Quantity</TableHead>
                  <TableHead>Start Price</TableHead>
                  <TableHead>End Price</TableHead>
                  <TableHead>P&L</TableHead>
                  <TableHead>Return %</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {Object.entries(run.results_json).map(([symbol, data]: [string, any], idx: number) => (
                  <TableRow key={idx}>
                    <TableCell className="font-mono">{symbol}</TableCell>
                    <TableCell className="text-xs">{data.qty}</TableCell>
                    <TableCell className="text-xs">{formatNumber(data.start_price)}</TableCell>
                    <TableCell className="text-xs">{formatNumber(data.end_price)}</TableCell>
                    <TableCell className={data.pnl >= 0 ? "text-green-600" : "text-red-600"}>
                      {formatNumber(data.pnl)}
                    </TableCell>
                    <TableCell className={data.return_pct >= 0 ? "text-green-600" : "text-red-600"}>
                      {formatPercent(data.return_pct)}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
