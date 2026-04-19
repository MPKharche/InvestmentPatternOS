"use client";
import { useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { screenerApi, type Screener, type ScreenerRules, type ScreenerCondition, type ScreenerTemplate } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import { toast } from "sonner";
import { Plus, Trash2, Save, ArrowLeft, GripVertical, Sparkles } from "lucide-react";

const FIELD_OPTIONS = [
  { value: "rsi", label: "RSI (14)" },
  { value: "sma_20", label: "SMA 20" },
  { value: "sma_50", label: "SMA 50" },
  { value: "sma_200", label: "SMA 200" },
  { value: "ema_20", label: "EMA 20" },
  { value: "macd", label: "MACD" },
  { value: "macd_hist", label: "MACD Histogram" },
  { value: "bb_upper", label: "Bollinger Upper" },
  { value: "bb_lower", label: "Bollinger Lower" },
  { value: "atr", label: "ATR" },
  { value: "close", label: "Close Price" },
  { value: "volume", label: "Volume" },
  { value: "pe", label: "P/E Ratio" },
  { value: "pb", label: "P/B Ratio" },
  { value: "roe", label: "ROE %" },
  { value: "debt_to_equity", label: "Debt/Equity" },
  { value: "dividend_yield", label: "Dividend Yield %" },
  { value: "beta", label: "Beta" },
  { value: "market_cap", label: "Market Cap" },
];

const OPERATOR_OPTIONS = [
  { value: ">", label: "greater than" },
  { value: "<", label: "less than" },
  { value: ">=", label: "≥" },
  { value: "<=", label: "≤" },
  { value: "==", label: "equals" },
  { value: "!=", label: "not equals" },
  { value: "between", label: "between" },
];

export default function ScreenerBuilderPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const editId = searchParams.get("id");

  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [assetClass, setAssetClass] = useState<"equity" | "mf">("equity");
  const [scope, setScope] = useState<"nifty50" | "nifty500" | "custom">("nifty500");
  const [customSymbols, setCustomSymbols] = useState("");
  const [logic, setLogic] = useState<"AND" | "OR">("AND");
  const [conditions, setConditions] = useState<ScreenerCondition[]>([
    { field: "rsi", operator: "<", value: 30 }
  ]);

  const [presets, setPresets] = useState<ScreenerTemplate[]>([]);
  const [presetsLoading, setPresetsLoading] = useState(false);
  const [presetCategory, setPresetCategory] = useState<string>("all");

  const [saving, setSaving] = useState(false);

  // Load existing screener if editing
  useEffect(() => {
    if (editId) {
      screenerApi.get(editId).then(s => {
        setName(s.name);
        setDescription(s.description || "");
        setAssetClass(s.asset_class);
        setScope(s.scope);
        setCustomSymbols(s.custom_symbols?.join(", ") || "");
        setLogic(s.rules.logic);
        setConditions(s.rules.conditions);
      }).catch(() => toast.error("Failed to load screener"));
    }
  }, [editId]);

  // Load presets
  useEffect(() => {
    setPresetsLoading(true);
    screenerApi.getPresets(presetCategory !== "all" ? presetCategory : undefined)
      .then(setPresets)
      .catch(() => toast.error("Failed to load presets"))
      .finally(() => setPresetsLoading(false));
  }, [presetCategory]);

  const addCondition = () => {
    setConditions([...conditions, { field: "rsi", operator: "<", value: 30 }]);
  };

  const removeCondition = (idx: number) => {
    setConditions(conditions.filter((_, i) => i !== idx));
  };

  const updateCondition = (idx: number, updates: Partial<ScreenerCondition>) => {
    const next = [...conditions];
    next[idx] = { ...next[idx], ...updates };
    setConditions(next);
  };

  const handleSave = async () => {
    if (!name.trim()) {
      toast.error("Name required");
      return;
    }
    if (conditions.length === 0) {
      toast.error("At least one condition required");
      return;
    }
    if (scope === "custom" && !customSymbols.trim()) {
      toast.error("Custom symbols required for custom scope");
      return;
    }

    const body = {
      name: name.trim(),
      description: description.trim() || undefined,
      asset_class: assetClass,
      scope,
      custom_symbols: scope === "custom" ? customSymbols.split(",").map(s => s.trim()).filter(Boolean) : undefined,
      rules: { logic, conditions },
    };

    setSaving(true);
    try {
      if (editId) {
        await screenerApi.update(editId, body);
        toast.success("Updated");
      } else {
        const created = await screenerApi.create(body);
        toast.success("Created");
        router.push(`/screener/${created.id}/results`);
        return;
      }
      router.push("/screener");
    } catch (e) {
      toast.error(editId ? "Update failed" : "Create failed");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-6 max-w-4xl">
      <div className="flex items-center gap-2">
        <Button variant="ghost" size="icon" onClick={() => router.back()}>
          <ArrowLeft className="h-4 w-4" />
        </Button>
        <h1 className="text-2xl font-bold">{editId ? "Edit Screener" : "Create Screener"}</h1>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Basic Info</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div>
            <Label>Name</Label>
            <Input value={name} onChange={e => setName(e.target.value)} placeholder="e.g., RSI Oversold Scan" />
          </div>
          <div>
            <Label>Description (optional)</Label>
            <Input value={description} onChange={e => setDescription(e.target.value)} placeholder="Brief description..." />
          </div>
          <div className="grid grid-cols-3 gap-4">
            <div>
              <Label>Asset Class</Label>
              <Select value={assetClass} onValueChange={v => setAssetClass(v as "equity" | "mf")}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="equity">Equity</SelectItem>
                  <SelectItem value="mf">Mutual Funds</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label>Scope</Label>
              <Select value={scope} onValueChange={v => setScope(v as "nifty50" | "nifty500" | "custom")}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="nifty50">Nifty 50</SelectItem>
                  <SelectItem value="nifty500">Nifty 500</SelectItem>
                  <SelectItem value="custom">Custom List</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
          {scope === "custom" && (
            <div>
              <Label>Custom Symbols (comma-separated)</Label>
              <Textarea value={customSymbols} onChange={e => setCustomSymbols(e.target.value)} placeholder="RELIANCE, TCS, INFY" rows={2} />
            </div>
          )}
        </CardContent>
      </Card>

      {/* Preset Templates */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Sparkles className="h-4 w-4" />
            Start from a Template
          </CardTitle>
          <p className="text-sm text-muted-foreground">
            Pick a pre-built rule set to get started quickly.
          </p>
        </CardHeader>
        <CardContent>
          <div className="flex items-center gap-2 mb-3">
            <Select value={presetCategory} onValueChange={setPresetCategory}>
              <SelectTrigger className="w-36">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All Categories</SelectItem>
                <SelectItem value="technical">Technical</SelectItem>
                <SelectItem value="fundamental">Fundamental</SelectItem>
                <SelectItem value="momentum">Momentum</SelectItem>
                <SelectItem value="value">Value</SelectItem>
                <SelectItem value="oscillator">Oscillator</SelectItem>
              </SelectContent>
            </Select>
          </div>

          {presetsLoading ? (
            <div className="text-sm text-muted-foreground">Loading templates...</div>
          ) : presets.length === 0 ? (
            <div className="text-sm text-muted-foreground">No templates available for this category.</div>
          ) : (
            <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
              {presets.map((tpl) => (
                <div
                  key={tpl.id}
                  className="p-3 border rounded-md bg-muted/20 hover:bg-muted/40 cursor-pointer transition-colors"
                  onClick={() => {
                    setLogic(tpl.rules_json.logic as "AND" | "OR");
                    setConditions(tpl.rules_json.conditions as ScreenerCondition[]);
                    toast.success(`Applied template: ${tpl.name}`);
                  }}
                >
                  <div className="flex items-center justify-between">
                    <span className="font-medium text-sm">{tpl.name}</span>
                    {tpl.tags && tpl.tags.length > 0 && (
                      <Badge variant="outline" className="text-[9px]">{tpl.tags[0]}</Badge>
                    )}
                  </div>
                  {tpl.description && (
                    <p className="text-xs text-muted-foreground mt-1 line-clamp-2">{tpl.description}</p>
                  )}
                  <div className="mt-2 text-xs text-muted-foreground">
                    {tpl.rules_json.conditions.length} conditions · {tpl.category}
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Rules</CardTitle>
          <p className="text-sm text-muted-foreground">Conditions are combined with {logic} logic.</p>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-center gap-2">
            <Label>Match when:</Label>
            <Select value={logic} onValueChange={v => setLogic(v as "AND" | "OR")}>
              <SelectTrigger className="w-20"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="AND">ALL</SelectItem>
                <SelectItem value="OR">ANY</SelectItem>
              </SelectContent>
            </Select>
            <span className="text-sm text-muted-foreground">conditions are met</span>
          </div>

          <div className="space-y-3">
            {conditions.map((cond, idx) => (
              <div key={idx} className="flex items-center gap-2 p-3 border rounded-md bg-muted/20">
                <GripVertical className="h-4 w-4 text-muted-foreground" />
                <div className="flex-1 grid grid-cols-4 gap-2">
                  <Select value={cond.field} onValueChange={v => updateCondition(idx, { field: v })}>
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent>
                      {FIELD_OPTIONS.map(f => <SelectItem key={f.value} value={f.value}>{f.label}</SelectItem>)}
                    </SelectContent>
                  </Select>
                  <Select value={cond.operator} onValueChange={v => updateCondition(idx, { operator: v })}>
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent>
                      {OPERATOR_OPTIONS.map(o => <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>)}
                    </SelectContent>
                  </Select>
                  {cond.operator === "between" ? (
                    <div className="flex gap-1 col-span-2">
                      <Input type="number" step="any" placeholder="min" value={cond.min ?? ""} onChange={e => updateCondition(idx, { min: parseFloat(e.target.value) || undefined })} />
                      <span className="self-center">and</span>
                      <Input type="number" step="any" placeholder="max" value={cond.max ?? ""} onChange={e => updateCondition(idx, { max: parseFloat(e.target.value) || undefined })} />
                    </div>
                  ) : (
                    <Input
                      type={cond.field.startsWith("pe") || cond.field.includes("rsi") || cond.field.includes("sma") ? "number" : "text"}
                      step="any"
                      placeholder="value"
                      value={cond.value ?? ""}
                      onChange={e => {
                        const val = e.target.value;
                        updateCondition(idx, { value: val === "" ? undefined : (cond.field === "rsi" || cond.field.includes("pe") ? parseFloat(val) : val) });
                      }}
                      className="col-span-2"
                    />
                  )}
                </div>
                <Button size="icon" variant="ghost" className="text-destructive" onClick={() => removeCondition(idx)}>
                  <Trash2 className="h-4 w-4" />
                </Button>
              </div>
            ))}
          </div>

          <Button variant="outline" size="sm" onClick={addCondition}>
            <Plus className="h-4 w-4 mr-1" /> Add Condition
          </Button>
        </CardContent>
      </Card>

      <div className="flex items-center gap-3">
        <Button onClick={handleSave} disabled={saving}>
          <Save className="h-4 w-4 mr-1" /> {saving ? "Saving..." : editId ? "Update" : "Create"}
        </Button>
        <Button variant="ghost" onClick={() => router.push("/screener")}>Cancel</Button>
      </div>
    </div>
  );
}
