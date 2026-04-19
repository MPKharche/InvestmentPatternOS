"use client";
import { useEffect, useState, useMemo } from "react";
import { useParams } from "next/navigation";
import { studioApi, type BacktestRun, type CompareRunsResponse, MetricDelta } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { toast } from "sonner";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Loader2, Play, GitCompare } from "lucide-react";

export default function BacktestRunsPage() {
  const params = useParams();
  const patternId = params.patternId as string;

  const [runs, setRuns] = useState<BacktestRun[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [compareOpen, setCompareOpen] = useState(false);
  const [compareResult, setCompareResult] = useState<CompareRunsResponse | null>(null);
  const [comparing, setComparing] = useState(false);

  useEffect(() => {
    loadRuns();
  }, [patternId]);

  const loadRuns = async () => {
    setLoading(true);
    try {
      const data = await studioApi.getBacktestRuns(patternId);
      setRuns(data);
    } catch {
      toast.error("Failed to load runs");
    } finally {
      setLoading(false);
    }
  };

  const toggleSelect = (id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const handleCompare = async () => {
    if (selectedIds.size < 2) return;
    setComparing(true);
    try {
      const res = await studioApi.compareBacktestRuns(patternId, Array.from(selectedIds));
      setCompareResult(res);
      setCompareOpen(true);
    } catch {
      toast.error("Comparison failed");
    } finally {
      setComparing(false);
    }
  };

  const formatDate = (s: string | null | undefined) => {
    if (!s) return "—";
    return new Date(s).toLocaleDateString();
  };

  const fmtPct = (v: number | null) => (v != null ? `${v >= 0 ? "+" : ""}${v.toFixed(2)}%` : "—");

  const getStatusVariant = (status: string) => {
    switch (status) {
      case "completed":
        return "default";
      case "running":
        return "secondary";
      case "failed":
        return "destructive";
      default:
        return "outline";
    }
  };

  return (
    <div className="space-y-6 max-w-6xl">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Backtest Runs</h1>
          <p className="text-muted-foreground text-sm">Historical backtest runs for this pattern</p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={loadRuns} disabled={loading}>
            <Loader2 className={`h-4 w-4 mr-1 ${loading ? "animate-spin" : ""}`} /> Refresh
          </Button>
          <Button onClick={handleCompare} disabled={selectedIds.size < 2}>
            <GitCompare className="h-4 w-4 mr-1" /> Compare Selected
          </Button>
        </div>
      </div>

      {loading ? (
        <div className="flex items-center justify-center py-12">
          <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
        </div>
      ) : runs.length === 0 ? (
        <Card>
          <CardContent className="py-8 text-center text-muted-foreground">
            No backtest runs yet. Run a backtest from the Studio to see results.
          </CardContent>
        </Card>
      ) : (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Runs History</CardTitle>
          </CardHeader>
          <CardContent>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-12"><input type="checkbox" checked={selectedIds.size === runs.length && runs.length>0} onChange={(e) => { if (e.target.checked) setSelectedIds(new Set(runs.map(r=>r.id))); else setSelectedIds(new Set()); }} /></TableHead>
                  <TableHead>Version</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Events</TableHead>
                  <TableHead>Success Rate</TableHead>
                  <TableHead>20d Avg Return</TableHead>
                  <TableHead>Started</TableHead>
                  <TableHead>Tags</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {runs.map((run) => (
                  <TableRow key={run.id}>
                    <TableCell>
                      <input
                        type="checkbox"
                        checked={selectedIds.has(run.id)}
                        onChange={() => toggleSelect(run.id)}
                        className="h-4 w-4 rounded border-gray-300"
                      />
                    </TableCell>
                    <TableCell className="font-mono text-xs">v{run.version_num}</TableCell>
                    <TableCell>
                      <Badge variant={getStatusVariant(run.status)}>{run.status}</Badge>
                    </TableCell>
                    <TableCell className="text-xs">{run.events_found}</TableCell>
                    <TableCell className={run.success_rate != null && run.success_rate >= 50 ? "text-green-400" : "text-red-400"}>
                      {run.success_rate?.toFixed(1) ?? "—"}%
                    </TableCell>
                    <TableCell className={fmtPct(run.avg_ret_20d)}>{fmtPct(run.avg_ret_20d)}</TableCell>
                    <TableCell className="text-xs text-muted-foreground">{formatDate(run.started_at)}</TableCell>
                    <TableCell>
                      {run.tags && run.tags.length > 0 ? (
                        <div className="flex flex-wrap gap-1">
                          {run.tags.map((t) => (
                            <Badge key={t} variant="outline" className="text-[10px] px-1">{t}</Badge>
                          ))}
                        </div>
                      ) : (
                        <span className="text-muted-foreground text-xs">—</span>
                      )}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}

      {/* Comparison Dialog */}
      <Dialog open={compareOpen} onOpenChange={setCompareOpen}>
        <DialogContent className="max-w-5xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Compare Runs</DialogTitle>
            <DialogDescription>Side-by-side metric comparison (baseline = first selected)</DialogDescription>
          </DialogHeader>
          {compareResult && (
            <div className="space-y-6">
              {/* Runs summary */}
              <div className="grid gap-4 md:grid-cols-2">
                {compareResult.runs.map((run) => (
                  <Card key={run.id}>
                    <CardHeader className="py-3">
                      <CardTitle className="text-xs font-medium">Run {run.id.slice(0, 8)}… — v{run.version_num}</CardTitle>
                    </CardHeader>
                    <CardContent className="py-2 text-xs space-y-1">
                      <div className="flex justify-between"><span>Status</span><span>{run.status}</span></div>
                      <div className="flex justify-between"><span>Events</span><span>{run.events_found}</span></div>
                      <div className="flex justify-between"><span>Success Rate</span><span className={run.success_rate != null && run.success_rate >= 50 ? "text-green-400" : "text-red-400"}>{run.success_rate?.toFixed(1) ?? "—"}%</span></div>
                      <div className="flex justify-between"><span>Avg 20d Return</span><span>{fmtPct(run.avg_ret_20d)}</span></div>
                      {run.tags && run.tags.length > 0 && (
                        <div className="flex flex-wrap gap-1 mt-2">
                          {run.tags.map(t => <Badge key={t} variant="outline" className="text-[9px]">{t}</Badge>)}
                        </div>
                      )}
                    </CardContent>
                  </Card>
                ))}
              </div>

              {/* Metrics delta table */}
              <Card>
                <CardHeader className="py-2">
                  <CardTitle className="text-sm">Metric Deltas</CardTitle>
                </CardHeader>
                <CardContent>
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Metric</TableHead>
                        <TableHead>Baseline</TableHead>
                        <TableHead>Comparison</TableHead>
                        <TableHead>Δ</TableHead>
                        <TableHead>Δ %</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {compareResult.metrics.map((m: MetricDelta, idx: number) => (
                        <TableRow key={idx}>
                          <TableCell className="font-medium text-xs">{m.metric}</TableCell>
                          <TableCell className="text-xs">{m.baseline != null ? m.baseline.toFixed(2) : "—"}</TableCell>
                          <TableCell className="text-xs">{m.comparison != null ? m.comparison.toFixed(2) : "—"}</TableCell>
                          <TableCell className={m.delta != null && m.delta > 0 ? "text-green-400" : m.delta != null && m.delta < 0 ? "text-red-400" : ""}>
                            {m.delta != null ? (m.delta >= 0 ? "+" : "") + m.delta.toFixed(2) : "—"}
                          </TableCell>
                          <TableCell className={m.delta_pct != null && m.delta_pct > 0 ? "text-green-400" : m.delta_pct != null && m.delta_pct < 0 ? "text-red-400" : ""}>
                            {m.delta_pct != null ? (m.delta_pct >= 0 ? "+" : "") + m.delta_pct.toFixed(2) + "%" : "—"}
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </CardContent>
              </Card>

              {/* Improved / Degraded badges */}
              <div className="flex gap-4 text-xs">
                <div className="flex items-center gap-2">
                  <span className="text-muted-foreground">Improved:</span>
                  <div className="flex gap-1">
                    {compareResult.improved_metrics.map(m => (
                      <Badge key={m} variant="secondary" className="text-[10px]">{m}</Badge>
                    ))}
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-muted-foreground">Degraded:</span>
                  <div className="flex gap-1">
                    {compareResult.degraded_metrics.map(m => (
                      <Badge key={m} variant="destructive" className="text-[10px]">{m}</Badge>
                    ))}
                  </div>
                </div>
              </div>
            </div>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={() => setCompareOpen(false)}>Close</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
