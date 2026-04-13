"use client";
import { useEffect, useState } from "react";
import { universeApi, type UniverseItem } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { toast } from "sonner";
import { Plus, Trash2, ToggleLeft, ToggleRight, Search } from "lucide-react";

export default function UniversePage() {
  const [items, setItems] = useState<UniverseItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [showAdd, setShowAdd] = useState(false);
  const [showAll, setShowAll] = useState(false);

  // Add form
  const [symbol, setSymbol] = useState("");
  const [exchange, setExchange] = useState("NSE");
  const [assetClass, setAssetClass] = useState("equity");
  const [name, setName] = useState("");
  const [adding, setAdding] = useState(false);

  const load = () => {
    setLoading(true);
    universeApi.list(!showAll).then(setItems).finally(() => setLoading(false));
  };

  useEffect(() => { load(); }, [showAll]);

  const filtered = items.filter(
    (i) =>
      i.symbol.toLowerCase().includes(search.toLowerCase()) ||
      (i.name ?? "").toLowerCase().includes(search.toLowerCase())
  );

  const handleToggle = async (item: UniverseItem) => {
    try {
      await universeApi.toggle(item.id);
      toast.success(`${item.symbol} ${item.active ? "paused" : "activated"}`);
      load();
    } catch {
      toast.error("Failed to toggle");
    }
  };

  const handleDelete = async (item: UniverseItem) => {
    if (!confirm(`Remove ${item.symbol} from universe?`)) return;
    try {
      await universeApi.remove(item.id);
      toast.success(`${item.symbol} removed`);
      load();
    } catch {
      toast.error("Failed to remove");
    }
  };

  const handleAdd = async () => {
    if (!symbol) return;
    setAdding(true);
    try {
      await universeApi.add({ symbol: symbol.toUpperCase(), exchange, asset_class: assetClass, name: name || undefined });
      toast.success(`${symbol.toUpperCase()} added`);
      setShowAdd(false);
      setSymbol(""); setName("");
      load();
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "Failed to add";
      toast.error(msg.includes("already exists") ? `${symbol} already in universe` : msg);
    } finally {
      setAdding(false);
    }
  };

  return (
    <div className="space-y-4 max-w-4xl">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Universe</h1>
          <p className="text-muted-foreground text-sm">Manage the list of symbols scanned by PatternOS</p>
        </div>
        <Button size="sm" onClick={() => setShowAdd(true)}>
          <Plus className="h-3 w-3 mr-1" /> Add Symbol
        </Button>
      </div>

      <div className="flex items-center gap-3">
        <div className="relative flex-1 max-w-sm">
          <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
          <Input
            placeholder="Search symbol or name..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="pl-8"
          />
        </div>
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <input
            type="checkbox"
            id="showAll"
            checked={showAll}
            onChange={(e) => setShowAll(e.target.checked)}
            className="h-4 w-4"
          />
          <label htmlFor="showAll">Show paused</label>
        </div>
        <Badge variant="outline">{filtered.length} symbols</Badge>
      </div>

      {loading ? (
        <div className="text-muted-foreground text-sm">Loading...</div>
      ) : (
        <div className="rounded-md border overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b bg-muted/50">
                <th className="text-left p-3 font-medium text-muted-foreground">Symbol</th>
                <th className="text-left p-3 font-medium text-muted-foreground">Name</th>
                <th className="text-left p-3 font-medium text-muted-foreground">Exchange</th>
                <th className="text-left p-3 font-medium text-muted-foreground">Class</th>
                <th className="text-left p-3 font-medium text-muted-foreground">Status</th>
                <th className="text-right p-3 font-medium text-muted-foreground">Actions</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((item) => (
                <tr key={item.id} className="border-b hover:bg-muted/20 transition-colors">
                  <td className="p-3 font-mono font-medium">{item.symbol}</td>
                  <td className="p-3 text-muted-foreground">{item.name ?? "—"}</td>
                  <td className="p-3"><Badge variant="outline" className="text-xs">{item.exchange}</Badge></td>
                  <td className="p-3 text-muted-foreground text-xs">{item.asset_class}</td>
                  <td className="p-3">
                    <Badge
                      variant={item.active ? "default" : "secondary"}
                      className={`text-xs ${item.active ? "bg-green-500/20 text-green-400" : ""}`}
                    >
                      {item.active ? "Active" : "Paused"}
                    </Badge>
                  </td>
                  <td className="p-3 text-right">
                    <div className="flex items-center justify-end gap-1">
                      <Button size="icon" variant="ghost" className="h-7 w-7" onClick={() => handleToggle(item)}>
                        {item.active ? <ToggleRight className="h-4 w-4 text-green-400" /> : <ToggleLeft className="h-4 w-4 text-muted-foreground" />}
                      </Button>
                      <Button size="icon" variant="ghost" className="h-7 w-7 text-destructive hover:text-destructive" onClick={() => handleDelete(item)}>
                        <Trash2 className="h-3.5 w-3.5" />
                      </Button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Add symbol dialog */}
      <Dialog open={showAdd} onOpenChange={setShowAdd}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle>Add Symbol</DialogTitle>
          </DialogHeader>
          <div className="space-y-3">
            <div>
              <Label className="text-xs">Symbol <span className="text-muted-foreground">(e.g. RELIANCE.NS for NSE)</span></Label>
              <Input value={symbol} onChange={(e) => setSymbol(e.target.value)} placeholder="RELIANCE.NS" />
            </div>
            <div>
              <Label className="text-xs">Name (optional)</Label>
              <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="Reliance Industries" />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label className="text-xs">Exchange</Label>
                <Select value={exchange} onValueChange={(v) => { if (v) setExchange(v); }}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {["NSE", "BSE", "NASDAQ", "NYSE", "OTHER"].map((e) => (
                      <SelectItem key={e} value={e}>{e}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label className="text-xs">Asset Class</Label>
                <Select value={assetClass} onValueChange={(v) => { if (v) setAssetClass(v); }}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {["equity", "etf", "mutual_fund", "commodity", "index"].map((c) => (
                      <SelectItem key={c} value={c}>{c}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>
            <Button className="w-full" onClick={handleAdd} disabled={adding || !symbol}>
              {adding ? "Adding..." : "Add Symbol"}
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
