"use client";
import { useEffect, useState } from "react";
import { analyticsApiExtended } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { toast } from "sonner";
import { TrendingUp, TrendingDown, BarChart3 } from "lucide-react";

export default function SectorHeatmapPage() {
  const [sectors, setSectors] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    analyticsApiExtended.sectors("1d", 30)
      .then(setSectors)
      .catch(() => toast.error("Failed to load sector data"))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <div className="text-muted-foreground text-sm">Loading sector heatmap...</div>;

  if (sectors.length === 0) {
    return (
      <div className="text-muted-foreground text-sm py-12 text-center">
        No sector data available yet. Run pattern scans to populate outcomes.
      </div>
    );
  }

  // Determine color scale based on return
  const maxReturn = Math.max(...sectors.map(s => Math.abs(s.avg_return)));
  const getColorClass = (ret: number) => {
    const intensity = Math.min(Math.abs(ret) / (maxReturn || 1), 1);
    if (ret >= 0) return `bg-green-500/${Math.round(20 + intensity * 80)}`;
    return `bg-red-500/${Math.round(20 + intensity * 80)}`;
  };

  return (
    <div className="space-y-6 max-w-5xl">
      <div>
        <h1 className="text-2xl font-bold">Sector Heatmap</h1>
        <p className="text-muted-foreground text-sm">Sector-wise performance (20-day avg return)</p>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
        {sectors.map((s) => (
          <Card key={s.sector} className={`${s.avg_return >= 0 ? "border-green-500/30" : "border-red-500/30"}`}>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-medium truncate" title={s.sector}>
                {s.sector}
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="flex items-center gap-2 mb-2">
                {s.avg_return >= 0 ? (
                  <TrendingUp className="h-4 w-4 text-green-500" />
                ) : (
                  <TrendingDown className="h-4 w-4 text-red-500" />
                )}
                <span className={`text-lg font-bold ${s.avg_return >= 0 ? "text-green-500" : "text-red-500"}`}>
                  {s.avg_return > 0 ? "+" : ""}{s.avg_return.toFixed(2)}%
                </span>
              </div>
              <div className="text-xs text-muted-foreground">
                {s.symbol_count} stocks tracked
              </div>
              <div className="text-xs text-muted-foreground mt-1">
                Best: <span className="font-mono">{s.best_performer}</span> (+{s.best_return?.toFixed(1)}%)
              </div>
              <div className="text-xs text-muted-foreground">
                Worst: <span className="font-mono">{s.worst_performer}</span> ({s.worst_return?.toFixed(1)}%)
              </div>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
