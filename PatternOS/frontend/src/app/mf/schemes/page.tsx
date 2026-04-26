"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { mfApi, type MFScheme } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { toast } from "sonner";
import { RefreshCw, Star } from "lucide-react";

export default function MFSchemesPage() {
  const [rows, setRows] = useState<MFScheme[]>([]);
  const [loading, setLoading] = useState(true);
  const [query, setQuery] = useState("");
  const [monitoredOnly, setMonitoredOnly] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const data = await mfApi.schemes(monitoredOnly, query || undefined);
      setRows(data);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Failed to load schemes");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    const id = window.setTimeout(() => {
      void load();
    }, query.trim() ? 250 : 0);
    return () => window.clearTimeout(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [monitoredOnly, query]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return rows;
    const stop = new Set([
      "fund",
      "mutual",
      "mf",
      "plan",
      "direct",
      "regular",
      "growth",
      "dividend",
      "option",
      "value",
      "val",
    ]);
    const tokens = q
      .split(/\s+/)
      .map((t) => t.trim())
      .filter((t) => t.length >= 2 && !stop.has(t))
      .slice(0, 8);
    const hay = (r: MFScheme) =>
      `${r.scheme_code} ${r.scheme_name ?? ""} ${r.amc_name ?? ""} ${r.family_name ?? ""} ${r.category ?? ""}`.toLowerCase();
    const strict = rows.filter((r) => tokens.every((t) => hay(r).includes(t)) || String(r.scheme_code).includes(q));
    if (strict.length > 0) return strict;
    return rows.filter((r) => tokens.some((t) => hay(r).includes(t)) || String(r.scheme_code).includes(q));
  }, [rows, query]);

  const linkQuery = (r: MFScheme) => `${r.scheme_name ?? `Scheme ${r.scheme_code}`} ${r.amc_name ?? ""}`.trim();
  const siteSearchHref = (site: string, r: MFScheme) =>
    `https://www.google.com/search?q=${encodeURIComponent(`site:${site} ${linkQuery(r)}`)}`;

  const toggleMonitored = async (schemeCode: number, next: boolean) => {
    try {
      await mfApi.updateScheme(schemeCode, { monitored: next });
      setRows((prev) => prev.map((r) => (r.scheme_code === schemeCode ? { ...r, monitored: next } : r)));
      toast.success(next ? "Added to watchlist" : "Removed from watchlist");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Update failed");
    }
  };

  return (
    <div className="space-y-4 max-w-6xl">
      <div className="flex flex-col md:flex-row md:items-start md:justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold">Schemes</h1>
          <p className="text-muted-foreground text-sm mt-1">
            Search schemes and mark a watchlist. Signals and metrics compute for monitored schemes.
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={load} disabled={loading}>
          <RefreshCw className="h-3 w-3 mr-1" /> Refresh
        </Button>
      </div>

      <div className="flex flex-col md:flex-row gap-3 items-stretch md:items-center">
        <Input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search by name or scheme code…"
          className="md:max-w-md"
        />
        <Button
          variant={monitoredOnly ? "default" : "outline"}
          size="sm"
          onClick={() => setMonitoredOnly((v) => !v)}
          className="md:ml-auto"
        >
          <Star className="h-3 w-3 mr-1" />
          {monitoredOnly ? "Watchlist" : "All schemes"}
        </Button>
      </div>

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm">Results</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="overflow-x-auto">
            <table className="min-w-[820px] w-full text-sm">
              <thead>
                <tr className="text-xs text-muted-foreground">
                  <th className="text-left py-2 pr-3">Scheme</th>
                  <th className="text-left py-2 pr-3">Category</th>
                  <th className="text-left py-2 pr-3">Risk</th>
                  <th className="text-left py-2 pr-3">Expense</th>
                  <th className="text-left py-2 pr-3">NAV</th>
                  <th className="text-left py-2 pr-3">Links</th>
                  <th className="text-left py-2 pr-3">Watch</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((r) => (
                  <tr key={r.scheme_code} className="border-t border-border/60">
                    <td className="py-2 pr-3">
                      <Link href={`/mf/schemes/${r.scheme_code}`} className="hover:underline">
                        <div className="font-medium">{r.scheme_name ?? `Scheme ${r.scheme_code}`}</div>
                        <div className="text-xs text-muted-foreground">AMFI {r.scheme_code}</div>
                      </Link>
                    </td>
                    <td className="py-2 pr-3 text-xs text-muted-foreground">{r.category ?? "—"}</td>
                    <td className="py-2 pr-3">
                      {r.risk_label ? <Badge variant="outline">{r.risk_label}</Badge> : <span className="text-xs text-muted-foreground">—</span>}
                    </td>
                    <td className="py-2 pr-3 text-xs text-muted-foreground">
                      {r.expense_ratio != null ? `${r.expense_ratio.toFixed(2)}%` : "—"}
                    </td>
                    <td className="py-2 pr-3 text-xs text-muted-foreground">
                      {r.latest_nav != null ? r.latest_nav.toFixed(4) : "—"}{" "}
                      {r.latest_nav_date ? <span className="text-[10px] opacity-70">({r.latest_nav_date})</span> : null}
                    </td>
                    <td className="py-2 pr-3 text-xs">
                      <div className="flex flex-wrap gap-2">
                        <a
                          className="text-sky-400 hover:underline"
                          href={r.valueresearch_url ?? siteSearchHref("valueresearchonline.com", r)}
                          target="_blank"
                          rel="noreferrer"
                        >
                          ValueResearch
                        </a>
                        <a
                          className="text-sky-400 hover:underline"
                          href={r.morningstar_url ?? siteSearchHref("morningstar.in", r)}
                          target="_blank"
                          rel="noreferrer"
                        >
                          Morningstar
                        </a>
                        <a
                          className="text-sky-400 hover:underline"
                          href={r.yahoo_finance_url ?? siteSearchHref("finance.yahoo.com", r)}
                          target="_blank"
                          rel="noreferrer"
                        >
                          Yahoo
                        </a>
                      </div>
                    </td>
                    <td className="py-2 pr-3">
                      <Button
                        size="xs"
                        variant={r.monitored ? "default" : "outline"}
                        onClick={() => toggleMonitored(r.scheme_code, !r.monitored)}
                      >
                        {r.monitored ? "Monitored" : "Monitor"}
                      </Button>
                    </td>
                  </tr>
                ))}
                {!filtered.length && (
                  <tr>
                    <td colSpan={7} className="py-8 text-center text-sm text-muted-foreground">
                      {loading ? "Loading…" : "No schemes found."}
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
