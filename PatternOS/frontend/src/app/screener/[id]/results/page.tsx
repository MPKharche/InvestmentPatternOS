"use client";
import { useEffect, useState } from "react";
import { screenerApi, type ScreenerResultItem, type ScreenerRun } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Play, BarChart3, Clock, CheckCircle2, XCircle } from "lucide-react";
import { useParams } from "next/navigation";
import { toast } from "sonner";

export default function ScreenerResultsPage() {
  const params = useParams();
  const screenerId = params.id as string;
  const runId = useSearchParams()?.get("run_id");

  const [results, setResults] = useState<ScreenerResultItem[]>([]);
  const [runs, setRuns] = useState<ScreenerRun[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedRunId, setSelectedRunId] = useState<string | null>(runId || null);

  useEffect(() => {
    loadData();
  }, [screenerId]);

  const loadData = async () => {
    setLoading(true);
    try {
      const [resultsData, runsData] = await Promise.all([
        screenerApi.getResults(screenerId, false, 500),
        screenerApi.getRuns(screenerId, 20),
      ]);
      setResults(resultsData);
      setRuns(runsData);
      if (!selectedRunId && runsData.length > 0) {
        setSelectedRunId(runsData[0].id);
      }
    } catch {
      toast.error("Failed to load");
    } finally {
      setLoading(false);
    }
  };

  const handleRun = async () => {
    try {
      const res = await screenerApi.run({ screener_id: screenerId, use_cache: false });
      toast.success(`Scan started: ${res.run_id}`);
      // Reload
      loadData();
    } catch {
      toast.error("Failed to start scan");
    }
  };

  // Filter results by selected run (we don't have run_id on results; assume latest)
  // For simplicity show latest results; in future we'd store run_id in results
  const displayResults = results;

  return (
    <div className="space-y-6 max-w-6xl">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Screener Results</h1>
          <p className="text-muted-foreground text-sm">Matched symbols and scores</p>
        </div>
        <Button onClick={handleRun}>
          <Play className="h-4 w-4 mr-1" /> Run Now
        </Button>
      </div>

      {/* Runs history */}
      {runs.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Recent Runs</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex flex-wrap gap-2">
              {runs.map(run => (
                <Badge
                  key={run.id}
                  variant={selectedRunId === run.id ? "default" : "outline"}
                  className={`cursor-pointer ${selectedRunId === run.id ? "bg-primary" : ""}`}
                  onClick={() => setSelectedRunId(run.id)}
                >
                  <Clock className="h-3 w-3 mr-1" />
                  {new Date(run.triggered_at).toLocaleDateString()}
                  <span className="ml-1 text-xs">{run.symbols_passed}/{run.symbols_total}</span>
                </Badge>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {loading ? (
        <div className="text-muted-foreground">Loading results...</div>
      ) : displayResults.length === 0 ? (
        <Card>
          <CardContent className="py-12 text-center text-muted-foreground">
            No results yet. Run the screener to see matches.
          </CardContent>
        </Card>
      ) : (
        <Card>
          <CardHeader>
            <CardTitle>Matches ({displayResults.length})</CardTitle>
          </CardHeader>
          <CardContent>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Symbol</TableHead>
                  <TableHead>Score</TableHead>
                  <TableHead>RSI</TableHead>
                  <TableHead>P/E</TableHead>
                  <TableHead>Close</TableHead>
                  <TableHead>Passed</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {displayResults.map(r => (
                  <TableRow key={r.id}>
                    <TableCell className="font-mono font-medium">{r.symbol}</TableCell>
                    <TableCell>
                      <div className="flex items-center gap-2">
                        <div className="w-16 h-2 bg-muted rounded-full overflow-hidden">
                          <div className="h-full bg-primary" style={{ width: `${r.score}%` }} />
                        </div>
                        <span className="text-xs">{r.score?.toFixed(1)}</span>
                      </div>
                    </TableCell>
                    <TableCell>{(r.metrics.rsi as number | undefined)?.toFixed(1) ?? "—"}</TableCell>
                    <TableCell>{(r.metrics.pe as number | undefined)?.toFixed(2) ?? "—"}</TableCell>
                    <TableCell>{(r.metrics.close as number | undefined)?.toFixed(2) ?? "—"}</TableCell>
                    <TableCell>
                      {r.passed ? (
                        <Badge variant="default" className="bg-green-500/20 text-green-600"><CheckCircle2 className="h-3 w-3 mr-1"/>Pass</Badge>
                      ) : (
                        <Badge variant="secondary"><XCircle className="h-3 w-3 mr-1"/>Fail</Badge>
                      )}
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
