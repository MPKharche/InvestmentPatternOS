"use client";
import { useEffect, useState } from "react";
import { screenerApi, type Screener } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Plus, Play, Pencil, Trash2, Search, BarChart3 } from "lucide-react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";

export default function ScreenerListPage() {
  const [screeners, setScreeners] = useState<Screener[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const router = useRouter();

  useEffect(() => {
    screenerApi.list().then(setScreeners).catch(() => toast.error("Failed to load screeners")).finally(() => setLoading(false));
  }, []);

  const filtered = screeners.filter(s =>
    s.name.toLowerCase().includes(search.toLowerCase()) ||
    (s.description && s.description.toLowerCase().includes(search.toLowerCase()))
  );

  const handleDelete = async (id: string, name: string) => {
    if (!confirm(`Delete "${name}"?`)) return;
    try {
      await screenerApi.delete(id);
      setScreeners(screeners.filter(s => s.id !== id));
      toast.success("Deleted");
    } catch {
      toast.error("Failed to delete");
    }
  };

  const handleRun = async (id: string, name: string) => {
    try {
      const res = await screenerApi.run({ screener_id: id, use_cache: true });
      toast.success(`Run started: ${res.run_id}`);
      // Navigate to results after a small delay
      setTimeout(() => router.push(`/screener/${id}/results?run_id=${res.run_id}`), 500);
    } catch (e) {
      toast.error("Failed to start scan");
    }
  };

  return (
    <div className="space-y-6 max-w-6xl">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Custom Screener</h1>
          <p className="text-muted-foreground text-sm">Build and run your own screening rules</p>
        </div>
        <Button onClick={() => router.push("/screener/builder")}>
          <Plus className="h-4 w-4 mr-1" /> Create Screener
        </Button>
      </div>

      <div className="flex items-center gap-3">
        <div className="relative flex-1 max-w-sm">
          <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
          <Input placeholder="Search screeners..." value={search} onChange={e => setSearch(e.target.value)} className="pl-8" />
        </div>
        <Badge variant="outline">{filtered.length} screeners</Badge>
      </div>

      {loading ? (
        <div className="text-muted-foreground text-sm">Loading...</div>
      ) : filtered.length === 0 ? (
        <Card>
          <CardContent className="py-12 text-center text-muted-foreground">
            {search ? "No matching screeners." : "No screeners yet. Create one to get started."}
          </CardContent>
        </Card>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {filtered.map(s => (
            <Card key={s.id} className="flex flex-col">
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <BarChart3 className="h-5 w-5 text-primary" />
                  <span className="truncate">{s.name}</span>
                </CardTitle>
                <CardDescription>
                  {s.scope === "nifty50" ? "Nifty 50" : s.scope === "nifty500" ? "Nifty 500" : "Custom list"} • {s.asset_class}
                  {s.description && <span className="block text-xs mt-1">{s.description}</span>}
                </CardDescription>
              </CardHeader>
              <CardContent className="flex-1 flex flex-col justify-between mt-auto">
                <div className="text-sm text-muted-foreground mb-4">
                  Logic: <Badge variant="secondary">{s.rules.logic}</Badge>
                  <span className="ml-2">{s.rules.conditions.length} conditions</span>
                </div>
                <div className="flex items-center gap-2 mt-auto">
                  <Button size="sm" className="flex-1" onClick={() => handleRun(s.id, s.name)}>
                    <Play className="h-4 w-4 mr-1" /> Run
                  </Button>
                  <Button size="sm" variant="outline" onClick={() => router.push(`/screener/builder?id=${s.id}`)}>
                    <Pencil className="h-4 w-4" />
                  </Button>
                  <Button size="sm" variant="destructive" onClick={() => handleDelete(s.id, s.name)}>
                    <Trash2 className="h-4 w-4" />
                  </Button>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
