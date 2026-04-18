"use client";

import { useEffect, useMemo, useState } from "react";
import { mfApi, type MFRulebook, type MFRulebookVersion } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";
import { RefreshCw, Plus, CheckCircle2, Pencil, FileText } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

export default function MFRulebooksPage() {
  const [rows, setRows] = useState<MFRulebook[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const [current, setCurrent] = useState<MFRulebookVersion | null>(null);
  const [versions, setVersions] = useState<MFRulebookVersion[]>([]);
  const [editorText, setEditorText] = useState("");
  const [metaName, setMetaName] = useState("");
  const [metaStatus, setMetaStatus] = useState<string>("active");
  const [savingMeta, setSavingMeta] = useState(false);
  const [savingVersion, setSavingVersion] = useState(false);

  const selected = useMemo(() => rows.find((r) => r.id === selectedId) ?? null, [rows, selectedId]);

  const defaultRulebookTemplate = useMemo(
    () =>
      JSON.stringify(
        {
          rulebook_type: "mf",
          signal_definitions: [
            { signal_type: "nav_52w_breakout", enabled: true, thresholds: { min_ret_30d_pct: 4.0 }, cooldown_days: 7 },
            { signal_type: "nav_momentum", enabled: true, thresholds: { min_ret_90d_pct: 8.0 }, cooldown_days: 7 },
            { signal_type: "concentration_risk", enabled: true, thresholds: { top5_pct: 55.0, single_pct: 12.0 }, cooldown_days: 30 },
          ],
        },
        null,
        2
      ),
    []
  );

  const loadRulebooks = async () => {
    setLoading(true);
    try {
      const list = await mfApi.rulebooks();
      setRows(list);
      if (!selectedId && list.length) setSelectedId(list[0]!.id);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Failed to load rulebooks");
    } finally {
      setLoading(false);
    }
  };

  const loadSelected = async (id: string) => {
    try {
      const [cur, vers] = await Promise.all([mfApi.rulebookCurrent(id), mfApi.rulebookVersions(id)]);
      setCurrent(cur);
      setVersions(vers);
      setEditorText(JSON.stringify(cur.rulebook_json, null, 2));
      const rb = rows.find((r) => r.id === id);
      if (rb) {
        setMetaName(rb.name);
        setMetaStatus(rb.status);
      }
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Failed to load rulebook details");
    }
  };

  const onSelect = (id: string) => {
    setSelectedId(id);
    void loadSelected(id);
  };

  useEffect(() => {
    void loadRulebooks();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (selectedId) void loadSelected(selectedId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedId]);

  const saveMeta = async () => {
    if (!selected) return;
    setSavingMeta(true);
    try {
      const updated = await mfApi.updateRulebook(selected.id, { name: metaName, status: metaStatus });
      setRows((prev) => prev.map((r) => (r.id === updated.id ? updated : r)));
      toast.success("Updated rulebook");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Failed to update rulebook");
    } finally {
      setSavingMeta(false);
    }
  };

  const saveNewVersion = async () => {
    if (!selected) return;
    let parsed: any;
    try {
      parsed = JSON.parse(editorText);
    } catch {
      toast.error("Invalid JSON");
      return;
    }
    setSavingVersion(true);
    try {
      const ver = await mfApi.createRulebookVersion(selected.id, { rulebook_json: parsed, change_summary: "UI edit", set_current: true });
      toast.success(`Saved v${ver.version}`);
      await loadSelected(selected.id);
      await loadRulebooks();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Failed to save new version");
    } finally {
      setSavingVersion(false);
    }
  };

  const activateVersion = async (version: number) => {
    if (!selected) return;
    try {
      await mfApi.activateRulebookVersion(selected.id, version);
      toast.success(`Activated v${version}`);
      await loadSelected(selected.id);
      await loadRulebooks();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Failed to activate version");
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold">MF Rulebooks</h1>
          <p className="text-muted-foreground text-sm mt-1">Versioned JSON rulebooks driving MF signals.</p>
        </div>
        <div className="flex items-center gap-2">
          <CreateRulebookDialog
            template={defaultRulebookTemplate}
            onCreated={async () => {
              await loadRulebooks();
            }}
          />
          <Button variant="outline" size="sm" onClick={loadRulebooks} disabled={loading}>
            <RefreshCw className="h-3 w-3 mr-1" /> Refresh
          </Button>
        </div>
      </div>

      <div className="grid gap-4 md:grid-cols-[280px_1fr]">
        <Card className="h-fit">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm">Rulebooks</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {rows.map((r) => (
              <button
                key={r.id}
                onClick={() => onSelect(r.id)}
                className={[
                  "w-full text-left rounded-md border px-3 py-2 transition-colors",
                  r.id === selectedId ? "bg-accent" : "hover:bg-accent/50",
                ].join(" ")}
              >
                <div className="flex items-center justify-between gap-2">
                  <div className="text-sm font-medium truncate">{r.name}</div>
                  <Badge variant={r.status === "active" ? "default" : "secondary"} className="text-[10px]">
                    {r.status}
                  </Badge>
                </div>
                <div className="text-xs text-muted-foreground mt-1">
                  v{r.current_version} · updated {new Date(r.updated_at).toLocaleDateString()}
                </div>
              </button>
            ))}
            {!rows.length && (
              <div className="py-8 text-center text-sm text-muted-foreground">{loading ? "Loading…" : "No rulebooks."}</div>
            )}
          </CardContent>
        </Card>

        <div className="space-y-4">
          {!selected ? (
            <Card>
              <CardContent className="py-10 text-center text-sm text-muted-foreground">Select a rulebook to edit.</CardContent>
            </Card>
          ) : (
            <>
              <Card>
                <CardHeader className="pb-3">
                  <CardTitle className="text-sm flex items-center gap-2">
                    <FileText className="h-4 w-4" /> {selected.name}
                  </CardTitle>
                </CardHeader>
                <CardContent className="grid gap-3 md:grid-cols-2">
                  <div className="space-y-1.5">
                    <Label>Name</Label>
                    <Input value={metaName} onChange={(e) => setMetaName(e.target.value)} />
                  </div>
                  <div className="space-y-1.5">
                    <Label>Status</Label>
                    <Select value={metaStatus} onValueChange={(v) => setMetaStatus(v ?? "inactive")}>
                      <SelectTrigger>
                        <SelectValue placeholder="Status" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="active">active</SelectItem>
                        <SelectItem value="inactive">inactive</SelectItem>
                        <SelectItem value="archived">archived</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="md:col-span-2 flex items-center justify-end gap-2">
                    <Button variant="outline" onClick={() => selectedId && loadSelected(selectedId)}>
                      <RefreshCw className="h-3 w-3 mr-1" /> Reload
                    </Button>
                    <Button onClick={saveMeta} disabled={savingMeta}>
                      <Pencil className="h-3 w-3 mr-1" /> Save meta
                    </Button>
                  </div>
                </CardContent>
              </Card>

              <Tabs defaultValue="current" className="w-full">
                <TabsList>
                  <TabsTrigger value="current">Current</TabsTrigger>
                  <TabsTrigger value="versions">Versions</TabsTrigger>
                </TabsList>
                <TabsContent value="current" className="space-y-3">
                  <Card>
                    <CardHeader className="pb-2">
                      <CardTitle className="text-sm">Rulebook JSON (current)</CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-3">
                      <Textarea
                        value={editorText}
                        onChange={(e) => setEditorText(e.target.value)}
                        className="min-h-[360px] font-mono text-xs"
                      />
                      <div className="flex items-center justify-end gap-2">
                        <Button onClick={saveNewVersion} disabled={savingVersion}>
                          <CheckCircle2 className="h-3 w-3 mr-1" /> Save new version
                        </Button>
                      </div>
                      {current && (
                        <div className="text-xs text-muted-foreground">
                          Current: v{current.version} · {current.change_summary ?? "—"} · {new Date(current.created_at).toLocaleString()}
                        </div>
                      )}
                    </CardContent>
                  </Card>
                </TabsContent>
                <TabsContent value="versions" className="space-y-3">
                  <Card>
                    <CardHeader className="pb-2">
                      <CardTitle className="text-sm">Versions</CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-2">
                      {versions.map((v) => (
                        <div key={v.id} className="flex items-center justify-between gap-3 rounded-md border px-3 py-2">
                          <div className="min-w-0">
                            <div className="text-sm font-medium truncate">v{v.version}</div>
                            <div className="text-xs text-muted-foreground truncate">
                              {v.change_summary ?? "—"} · {new Date(v.created_at).toLocaleString()}
                            </div>
                          </div>
                          <div className="flex items-center gap-2 shrink-0">
                            <Button
                              variant="outline"
                              size="sm"
                              onClick={() => {
                                setEditorText(JSON.stringify(v.rulebook_json, null, 2));
                                toast.message(`Loaded v${v.version} into editor (not saved)`);
                              }}
                            >
                              View
                            </Button>
                            <Button size="sm" onClick={() => activateVersion(v.version)} disabled={selected.current_version === v.version}>
                              Activate
                            </Button>
                          </div>
                        </div>
                      ))}
                      {!versions.length && <div className="py-6 text-center text-sm text-muted-foreground">No versions.</div>}
                    </CardContent>
                  </Card>
                </TabsContent>
              </Tabs>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

function CreateRulebookDialog({ template, onCreated }: { template: string; onCreated: () => void | Promise<void> }) {
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("MF Custom v1");
  const [status, setStatus] = useState("active");
  const [jsonText, setJsonText] = useState(template);
  const [saving, setSaving] = useState(false);

  const create = async () => {
    let parsed: any;
    try {
      parsed = JSON.parse(jsonText);
    } catch {
      toast.error("Invalid JSON");
      return;
    }
    setSaving(true);
    try {
      await mfApi.createRulebook({ name, status, rulebook_json: parsed, change_summary: "Created in UI" });
      toast.success("Created rulebook");
      setOpen(false);
      await onCreated();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Failed to create rulebook");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger
        render={
          <Button size="sm">
            <Plus className="h-3 w-3 mr-1" /> New
          </Button>
        }
      />
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>Create MF rulebook</DialogTitle>
        </DialogHeader>
        <div className="grid gap-3 md:grid-cols-2">
          <div className="space-y-1.5">
            <Label>Name</Label>
            <Input value={name} onChange={(e) => setName(e.target.value)} />
          </div>
          <div className="space-y-1.5">
            <Label>Status</Label>
            <Select value={status} onValueChange={(v) => setStatus(v ?? "active")}>
              <SelectTrigger>
                <SelectValue placeholder="Status" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="active">active</SelectItem>
                <SelectItem value="inactive">inactive</SelectItem>
                <SelectItem value="archived">archived</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="md:col-span-2 space-y-1.5">
            <Label>Rulebook JSON</Label>
            <Textarea value={jsonText} onChange={(e) => setJsonText(e.target.value)} className="min-h-[320px] font-mono text-xs" />
          </div>
        </div>
        <DialogFooter>
          <Button onClick={create} disabled={saving}>
            Create
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
