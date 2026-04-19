"use client";
import { useEffect, useState, useMemo } from "react";
import { screenerApi, type ScreenerResultItem, type ScreenerRun } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import {
  Play,
  Clock,
  CheckCircle2,
  XCircle,
  ArrowUpDown,
  ChevronLeft,
  ChevronRight,
  Search,
  Filter,
} from "lucide-react";
import { useParams, useSearchParams } from "next/navigation";
import { toast } from "sonner";

type SortField = "symbol" | "score" | "rsi" | "pe" | "close";
type SortDir = "asc" | "desc";
type FilterStatus = "all" | "passed" | "failed";

const PAGE_SIZE = 50;

export default function ScreenerResultsPage() {
  const params = useParams();
  const screenerId = params.id as string;
  const runId = useSearchParams()?.get("run_id");

  const [results, setResults] = useState<ScreenerResultItem[]>([]);
  const [runs, setRuns] = useState<ScreenerRun[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedRunId, setSelectedRunId] = useState<string | null>(runId || null);

  // Filter / Sort / Pagination state
  const [searchQuery, setSearchQuery] = useState("");
  const [filterStatus, setFilterStatus] = useState<FilterStatus>("all");
  const [sortField, setSortField] = useState<SortField>("score");
  const [sortDir, setSortDir] = useState<SortDir>("desc");
  const [page, setPage] = useState(1);

  useEffect(() => {
    loadData();
  }, [screenerId]);

  const loadData = async () => {
    setLoading(true);
    try {
      const [resultsData, runsData] = await Promise.all([
        screenerApi.getResults(screenerId, false, 1000), // fetch up to 1000 for client-side handling
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
      loadData();
    } catch {
      toast.error("Failed to start scan");
    }
  };

  // Derived: filter → sort → paginate
  const filteredAndSorted = useMemo(() => {
    let arr = [...results];

    // Search by symbol
    if (searchQuery.trim()) {
      const q = searchQuery.trim().toUpperCase();
      arr = arr.filter((r) => r.symbol.toUpperCase().includes(q));
    }

    // Filter by passed/failed
    if (filterStatus === "passed") arr = arr.filter((r) => r.passed);
    else if (filterStatus === "failed") arr = arr.filter((r) => !r.passed);

    // Sort
    arr.sort((a, b) => {
      let aVal: number | string | null = null;
      let bVal: number | string | null = null;

      switch (sortField) {
        case "symbol":
          aVal = a.symbol;
          bVal = b.symbol;
          break;
        case "score":
          aVal = a.score ?? 0;
          bVal = b.score ?? 0;
          break;
        case "rsi":
          aVal = (a.metrics.rsi as number | undefined) ?? 0;
          bVal = (b.metrics.rsi as number | undefined) ?? 0;
          break;
        case "pe":
          aVal = (a.metrics.pe as number | undefined) ?? 0;
          bVal = (b.metrics.pe as number | undefined) ?? 0;
          break;
        case "close":
          aVal = (a.metrics.close as number | undefined) ?? 0;
          bVal = (b.metrics.close as number | undefined) ?? 0;
          break;
      }

      if (typeof aVal === "number" && typeof bVal === "number") {
        return sortDir === "asc" ? aVal - bVal : bVal - aVal;
      }
      return sortDir === "asc"
        ? String(aVal).localeCompare(String(bVal))
        : String(bVal).localeCompare(String(aVal));
    });

    return arr;
  }, [results, searchQuery, filterStatus, sortField, sortDir]);

  // Pagination
  const totalPages = Math.ceil(filteredAndSorted.length / PAGE_SIZE);
  const pageResults = useMemo(() => {
    const start = (page - 1) * PAGE_SIZE;
    return filteredAndSorted.slice(start, start + PAGE_SIZE);
  }, [filteredAndSorted, page]);

  // Reset to page 1 when filters change
  useEffect(() => {
    setPage(1);
  }, [searchQuery, filterStatus, sortField, sortDir]);

  const handleSort = (field: SortField) => {
    if (sortField === field) {
      setSortDir(sortDir === "asc" ? "desc" : "asc");
    } else {
      setSortField(field);
      setSortDir("desc");
    }
  };

  const SortIcon = ({ field }: { field: SortField }) => (
    <ArrowUpDown
      className={`ml-1 h-3 w-3 inline ${sortField === field ? "text-primary" : "text-muted-foreground/50"}`}
    />
  );

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
              {runs.map((run) => (
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

      {/* Filters toolbar */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base">Results ({filteredAndSorted.length} total)</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="flex flex-wrap gap-3">
            {/* Search */}
            <div className="relative flex-1 min-w-[200px]">
              <Search className="absolute left-2 top-2 h-4 w-4 text-muted-foreground" />
              <Input
                placeholder="Search symbol..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="pl-8 h-8 text-xs"
              />
            </div>

            {/* Status filter */}
            <div className="flex items-center gap-2">
              <Filter className="h-4 w-4 text-muted-foreground" />
              <select
                value={filterStatus}
                onChange={(e) => setFilterStatus(e.target.value as FilterStatus)}
                className="h-8 rounded border border-border bg-muted px-2 text-xs"
              >
                <option value="all">All</option>
                <option value="passed">Passed Only</option>
                <option value="failed">Failed Only</option>
              </select>
            </div>
          </div>

          {/* Active filters display */}
          {(searchQuery || filterStatus !== "all") && (
            <div className="flex items-center gap-2 text-xs text-muted-foreground">
              <span>Active filters:</span>
              {searchQuery && (
                <Badge variant="secondary" className="text-[10px]">
                  Symbol: {searchQuery}
                  <button onClick={() => setSearchQuery("")} className="ml-1 hover:text-destructive">
                    ×
                  </button>
                </Badge>
              )}
              {filterStatus !== "all" && (
                <Badge variant="secondary" className="text-[10px]">
                  {filterStatus === "passed" ? "Passed" : "Failed"}
                  <button onClick={() => setFilterStatus("all")} className="ml-1 hover:text-destructive">
                    ×
                  </button>
                </Badge>
              )}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Results table */}
      {loading ? (
        <div className="text-muted-foreground text-center py-12">Loading results...</div>
      ) : filteredAndSorted.length === 0 ? (
        <Card>
          <CardContent className="py-12 text-center text-muted-foreground">
            No results match the current filters.
          </CardContent>
        </Card>
      ) : (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">
              Matches ({filteredAndSorted.length}) — Page {page} of {totalPages || 1}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead
                    className="cursor-pointer hover:bg-muted/50"
                    onClick={() => handleSort("symbol")}
                  >
                    Symbol <SortIcon field="symbol" />
                  </TableHead>
                  <TableHead
                    className="cursor-pointer hover:bg-muted/50"
                    onClick={() => handleSort("score")}
                  >
                    Score <SortIcon field="score" />
                  </TableHead>
                  <TableHead
                    className="cursor-pointer hover:bg-muted/50"
                    onClick={() => handleSort("rsi")}
                  >
                    RSI <SortIcon field="rsi" />
                  </TableHead>
                  <TableHead
                    className="cursor-pointer hover:bg-muted/50"
                    onClick={() => handleSort("pe")}
                  >
                    P/E <SortIcon field="pe" />
                  </TableHead>
                  <TableHead
                    className="cursor-pointer hover:bg-muted/50"
                    onClick={() => handleSort("close")}
                  >
                    Close <SortIcon field="close" />
                  </TableHead>
                  <TableHead>Passed</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {pageResults.map((r) => (
                  <TableRow key={r.id}>
                    <TableCell className="font-mono font-medium">{r.symbol}</TableCell>
                    <TableCell>
                      <div className="flex items-center gap-2">
                        <div className="w-16 h-2 bg-muted rounded-full overflow-hidden">
                          <div className="h-full bg-primary" style={{ width: `${Math.min(r.score, 100)}%` }} />
                        </div>
                        <span className="text-xs">{r.score?.toFixed(1)}</span>
                      </div>
                    </TableCell>
                    <TableCell>{(r.metrics.rsi as number | undefined)?.toFixed(1) ?? "—"}</TableCell>
                    <TableCell>{(r.metrics.pe as number | undefined)?.toFixed(2) ?? "—"}</TableCell>
                    <TableCell>{(r.metrics.close as number | undefined)?.toFixed(2) ?? "—"}</TableCell>
                    <TableCell>
                      {r.passed ? (
                        <Badge variant="default" className="bg-green-500/20 text-green-600">
                          <CheckCircle2 className="h-3 w-3 mr-1" /> Pass
                        </Badge>
                      ) : (
                        <Badge variant="secondary">
                          <XCircle className="h-3 w-3 mr-1" /> Fail
                        </Badge>
                      )}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>

            {/* Pagination */}
            {totalPages > 1 && (
              <div className="flex items-center justify-between pt-4">
                <div className="text-xs text-muted-foreground">
                  Showing {(page - 1) * PAGE_SIZE + 1}–{Math.min(page * PAGE_SIZE, filteredAndSorted.length)} of{" "}
                  {filteredAndSorted.length} results
                </div>
                <div className="flex items-center gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setPage((p) => Math.max(1, p - 1))}
                    disabled={page === 1}
                  >
                    <ChevronLeft className="h-4 w-4" />
                  </Button>
                  <div className="text-sm">
                    Page {page} of {totalPages}
                  </div>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                    disabled={page === totalPages}
                  >
                    <ChevronRight className="h-4 w-4" />
                  </Button>
                </div>
              </div>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  );
}
