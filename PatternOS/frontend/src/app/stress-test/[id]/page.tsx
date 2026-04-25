"use client";
import { useEffect, useState } from "react";
import { stressTestApi, type PortfolioOut } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Play, Trash2, RefreshCw } from "lucide-react";
import { useParams, useRouter } from "next/navigation";
import { toast } from "sonner";

export default function StressTestPortfolioDetailPage() {
  const params = useParams();
  const portfolioId = params.id as string;
  const router = useRouter();

  const [portfolio, setPortfolio] = useState<PortfolioOut | null>(null);
  const [runs, setRuns] = useState<Array<any>>([]);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);

  useEffect(() => {
    loadPortfolio();
    loadRuns();
  }, [portfolioId]);

  const loadPortfolio = async () => {
    try {
      const data = await stressTestApi.getPortfolio(portfolioId);
      setPortfolio(data);
    } catch {
      toast.error("Failed to load portfolio");
    }
  };

  const loadRuns = async () => {
    try {
      const data = await stressTestApi.getPortfolioRuns(portfolioId);
      setRuns(data);
    } catch {
      toast.error("Failed to load runs");
    }
  };

  const handleRunStressTest = async () => {
    if (!portfolio) return;
    setRunning(true);
    try {
      // Use default scenario for now
      const result = await stressTestApi.runStressTest(portfolioId, {
        scenario: "2020_covid"
      });
      toast.success("Stress test started!");
      setRunning(false);
      loadRuns();
    } catch (e) {
      setRunning(false);
      toast.error(`Failed to start stress test: ${e instanceof Error ? e.message : "Unknown error"}`);
    }
  };

  const handleDeletePosition = (index: number) => {
    if (!portfolio) return;
    const confirm = window.confirm("Remove this position?");
    if (confirm) {
      // TODO: implement position deletion
      toast.error("Position deletion not implemented yet");
    }
  };

  if (!portfolio) {
    if (loading) {
      return (
        <div className="flex items-center justify-center py-12">
          <div className="text-muted-foreground">Loading portfolio...</div>
        </div>
      );
    }
    return (
      <div className="flex items-center justify-center py-12">
        <div className="text-muted-foreground">Portfolio not found</div>
      </div>
    );
  }

  return (
    <div className="space-y-6 max-w-4xl">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">{portfolio.name}</h1>
        <div className="flex gap-2">
          <Button
            variant="outline"
            onClick={handleRunStressTest}
            disabled={running || !portfolio.positions_json.length}
          >
            {running ? <RefreshCw className="h-4 w-4 mr-2 animate-spin" /> : <Play className="h-4 w-4 mr-2" />}
            Run Stress Test
          </Button>
          <Button
            variant="destructive"
            onClick={() => {
              if (window.confirm("Delete this portfolio?")) {
                // TODO: implement delete
                toast.error("Delete not implemented yet");
              }
            }}
          >
            <Trash2 className="h-4 w-4" />
          </Button>
        </div>
      </div>

      {/* Positions */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Positions ({portfolio.positions_json.length})</CardTitle>
        </CardHeader>
        <CardContent>
          {portfolio.positions_json.length === 0 ? (
            <p className="text-muted-foreground text-center py-4">No positions in this portfolio</p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Symbol</TableHead>
                  <TableHead>Quantity</TableHead>
                  <TableHead>Avg Price</TableHead>
                  <TableHead>Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {portfolio.positions_json.map((pos: any, idx: number) => (
                  <TableRow key={idx}>
                    <TableCell className="font-mono">{pos.symbol}</TableCell>
                    <TableCell className="text-xs">{pos.qty}</TableCell>
                    <TableCell className="text-xs">{pos.avg_price}</TableCell>
                    <TableCell>
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => handleDeletePosition(idx)}
                      >
                        Remove
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      {/* Stress Test Runs */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Stress Test Runs</CardTitle>
        </CardHeader>
        <CardContent>
          {runs.length === 0 ? (
            <p className="text-muted-foreground text-center py-4">No stress test runs yet</p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Scenario</TableHead>
                  <TableHead>Period</TableHead>
                  <TableHead>Initial Value</TableHead>
                  <TableHead>Final Value</TableHead>
                  <TableHead>Max Drawdown</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {runs.map((run: any, idx: number) => {
                  const statusClass = run.status === "completed"
                    ? "text-green-600"
                    : run.status === "failed"
                    ? "text-red-600"
                    : "text-yellow-600";
                  return (
                    <TableRow key={idx}>
                      <TableCell>{run.scenario}</TableCell>
                      <TableCell className="text-xs">
                        {new Date(run.start_date).toLocaleDateString()} to{' '}
                        {new Date(run.end_date).toLocaleDateString()}
                      </TableCell>
                      <TableCell className="text-xs text-right">{run.initial_value.toLocaleString()}</TableCell>
                      <TableCell className={run.final_value === null ? "text-muted-foreground" : "text-xs text-right"}>
                        {run.final_value !== null ? run.final_value.toLocaleString() : "—"}
                      </TableCell>
                      <TableCell className={run.max_drawdown_pct === null ? "text-muted-foreground" : "text-xs text-right"}>
                        {run.max_drawdown_pct !== null
                          ? `${run.max_drawdown_pct.toFixed(2)}%`
                          : "—"}
                      </TableCell>
                      <TableCell className={`text-xs ${statusClass}`}>
                        {run.status}
                      </TableCell>
                      <TableCell className="text-xs">
                        <a href={`/stress-test/run/${run.id}`} className="hover:underline">
                          Details
                        </a>
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
