"use client";
import { useEffect, useRef, useState, useCallback } from "react";
import {
  patternsApi,
  scannerApi,
  studioApi,
  type Pattern,
  type ChatMessage,
  type ChatResponse,
  type PatternEvent,
  type BacktestRun,
  type PatternStudyResult,
} from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Separator } from "@/components/ui/separator";
import { BacktestResults } from "@/components/backtest-results";
import { toast } from "sonner";
import {
  FileText,
  ImageIcon,
  Paperclip,
  Play,
  Plus,
  Send,
  X,
  BarChart2,
  List,
  BookOpen,
  MessageSquare,
  ExternalLink,
  RefreshCw,
  Loader2,
} from "lucide-react";

const BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api/v1";
const ACCEPT = ".jpg,.jpeg,.png,.webp,.gif,.pdf,.docx,.doc,.txt,.md";

type ActiveTab = "define" | "backtest" | "events" | "study";
type AttachedFile = { file: File; preview: string | null };

// ─── Helpers ─────────────────────────────────────────────────────────────────

function pct(v: number | null | undefined, decimals = 2): string {
  if (v == null) return "—";
  return `${v >= 0 ? "+" : ""}${v.toFixed(decimals)}%`;
}

function pctColor(v: number | null | undefined, invert = false): string {
  if (v == null) return "text-muted-foreground";
  const positive = invert ? v < 0 : v > 0;
  return positive ? "text-green-400" : v === 0 ? "text-muted-foreground" : "text-red-400";
}

function OutcomeBadge({ outcome }: { outcome: string | null }) {
  if (!outcome) return <Badge variant="outline">—</Badge>;
  const map: Record<string, string> = {
    success: "bg-green-500/20 text-green-400 border-green-500/30",
    failure: "bg-red-500/20 text-red-400 border-red-500/30",
    neutral: "bg-gray-500/20 text-gray-400 border-gray-500/30",
    pending: "bg-yellow-500/20 text-yellow-400 border-yellow-500/30",
  };
  return (
    <Badge className={`text-xs capitalize ${map[outcome] ?? "bg-muted"}`}>
      {outcome}
    </Badge>
  );
}

// ─── File icon ────────────────────────────────────────────────────────────────

function FileIcon({ name }: { name: string }) {
  const ext = name.split(".").pop()?.toLowerCase() ?? "";
  if (["jpg", "jpeg", "png", "webp", "gif"].includes(ext))
    return <ImageIcon className="h-3.5 w-3.5 text-blue-400" />;
  return <FileText className="h-3.5 w-3.5 text-yellow-400" />;
}

// ─── Collapsible JSON block ───────────────────────────────────────────────────

function CollapsibleCode({ code }: { code: string }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="mt-1">
      <button
        onClick={() => setOpen((o) => !o)}
        className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground transition-colors"
      >
        <FileText className="h-3 w-3" />
        {open ? "Hide rulebook JSON" : "View rulebook JSON"}
        <span className="text-[10px] opacity-60">{open ? "▲" : "▼"}</span>
      </button>
      {open && (
        <pre className="mt-2 text-xs bg-black/40 border border-border rounded p-3 overflow-auto max-h-64 text-green-400 font-mono">
          {code}
        </pre>
      )}
    </div>
  );
}

// ─── Parse message ────────────────────────────────────────────────────────────

function parseMessageContent(raw: string): { text: string; jsonBlocks: string[] } {
  const jsonBlocks: string[] = [];
  const text = raw
    .replace(/```json\s*([\s\S]+?)\s*```/g, (_, json) => {
      jsonBlocks.push(json.trim());
      return "";
    })
    .trim();
  return { text, jsonBlocks };
}

// ─── Chat bubble ──────────────────────────────────────────────────────────────

function ChatBubble({ msg }: { msg: ChatMessage }) {
  const isUser = msg.role === "user";
  const attachMatch = msg.content.match(/^\[Attached: (.+?)\]\n?([\s\S]*)/);
  const files = attachMatch ? attachMatch[1].split(", ") : [];
  const rawText = attachMatch ? attachMatch[2] : msg.content;
  const { text, jsonBlocks } = isUser
    ? { text: rawText, jsonBlocks: [] }
    : parseMessageContent(rawText);

  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
      <div className={`max-w-[82%] flex flex-col gap-1.5 ${isUser ? "items-end" : "items-start"}`}>
        {files.length > 0 && (
          <div className="flex flex-wrap gap-1">
            {files.map((f, i) => (
              <span
                key={i}
                className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-blue-500/20 text-blue-300 text-xs border border-blue-500/30"
              >
                <FileIcon name={f} />
                {f}
              </span>
            ))}
          </div>
        )}
        {text && (
          <div
            className={`rounded-lg px-4 py-2.5 text-sm whitespace-pre-wrap leading-relaxed ${
              isUser ? "bg-primary text-primary-foreground" : "bg-muted text-foreground"
            }`}
          >
            {text}
            {jsonBlocks.map((j, i) => (
              <CollapsibleCode key={i} code={j} />
            ))}
          </div>
        )}
        {!text && jsonBlocks.length > 0 && (
          <div className="bg-muted rounded-lg px-4 py-2.5 text-sm w-full">
            {jsonBlocks.map((j, i) => (
              <CollapsibleCode key={i} code={j} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

// ─── Rulebook preview ─────────────────────────────────────────────────────────

function RulebookPreview({
  json,
  onEdit,
}: {
  json: Record<string, unknown>;
  onEdit: (v: string) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [raw, setRaw] = useState(JSON.stringify(json, null, 2));
  const [parseErr, setParseErr] = useState("");

  const handleSave = () => {
    try {
      JSON.parse(raw);
      setParseErr("");
      setEditing(false);
      onEdit(raw);
    } catch {
      setParseErr("Invalid JSON — fix syntax before saving.");
    }
  };

  return (
    <div className="space-y-2">
      {editing ? (
        <>
          <textarea
            className="w-full h-72 text-xs font-mono bg-muted/50 rounded p-2 text-green-400 resize-none border border-border focus:outline-none"
            value={raw}
            onChange={(e) => {
              setRaw(e.target.value);
              setParseErr("");
            }}
          />
          {parseErr && <p className="text-destructive text-xs">{parseErr}</p>}
          <div className="flex gap-2">
            <Button size="sm" onClick={handleSave}>
              Save Changes
            </Button>
            <Button
              size="sm"
              variant="outline"
              onClick={() => {
                setEditing(false);
                setRaw(JSON.stringify(json, null, 2));
              }}
            >
              Cancel
            </Button>
          </div>
        </>
      ) : (
        <>
          <pre className="text-xs bg-muted/50 rounded p-3 overflow-auto max-h-72 text-green-400">
            {JSON.stringify(json, null, 2)}
          </pre>
          <Button
            size="sm"
            variant="outline"
            className="w-full text-xs"
            onClick={() => setEditing(true)}
          >
            Edit Rulebook
          </Button>
        </>
      )}
    </div>
  );
}

// ─── Attachment strip ─────────────────────────────────────────────────────────

function AttachmentStrip({
  files,
  onRemove,
}: {
  files: AttachedFile[];
  onRemove: (i: number) => void;
}) {
  if (!files.length) return null;
  return (
    <div className="flex flex-wrap gap-2 px-3 pt-2">
      {files.map((af, i) => (
        <div
          key={i}
          className="relative group flex items-center gap-1.5 bg-muted border border-border rounded px-2 py-1 text-xs"
        >
          {af.preview ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={af.preview} alt={af.file.name} className="h-8 w-8 object-cover rounded" />
          ) : (
            <FileIcon name={af.file.name} />
          )}
          <span className="max-w-[80px] truncate text-muted-foreground">{af.file.name}</span>
          <button onClick={() => onRemove(i)} className="ml-1 text-muted-foreground hover:text-destructive">
            <X className="h-3 w-3" />
          </button>
        </div>
      ))}
    </div>
  );
}

// ─── DEFINE TAB ──────────────────────────────────────────────────────────────

function DefineTab({
  history,
  sending,
  rulebookDraft,
  attachments,
  input,
  setInput,
  setAttachments,
  send,
  handleRulebookEdit,
  fileInputRef,
}: {
  history: ChatMessage[];
  sending: boolean;
  rulebookDraft: Record<string, unknown> | null;
  attachments: AttachedFile[];
  input: string;
  setInput: (v: string) => void;
  setAttachments: React.Dispatch<React.SetStateAction<AttachedFile[]>>;
  send: () => void;
  handleRulebookEdit: (raw: string) => void;
  fileInputRef: React.RefObject<HTMLInputElement | null>;
}) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [history]);

  const removeAttachment = (i: number) => {
    setAttachments((prev) => {
      const copy = [...prev];
      if (copy[i].preview) URL.revokeObjectURL(copy[i].preview!);
      copy.splice(i, 1);
      return copy;
    });
  };

  return (
    <div className="flex gap-4 flex-1 min-h-0">
      {/* Chat */}
      <div className="flex flex-col flex-1 min-w-0">
        {history.length === 0 && (
          <Card className="mb-3 border-amber-500/30 bg-amber-500/5">
            <CardContent className="p-4">
              <p className="text-xs font-semibold text-amber-400 mb-2">Image Analysis Workflow</p>
              <div className="grid grid-cols-4 gap-2 text-xs text-muted-foreground">
                <div className="flex flex-col gap-1">
                  <span className="text-amber-400 font-medium">Step 1</span>
                  Upload chart image
                </div>
                <div className="flex flex-col gap-1">
                  <span className="text-amber-400 font-medium">Step 2</span>
                  Describe the pattern annotations
                </div>
                <div className="flex flex-col gap-1">
                  <span className="text-amber-400 font-medium">Step 3</span>
                  LLM extracts rules &rarr; builds rulebook
                </div>
                <div className="flex flex-col gap-1">
                  <span className="text-amber-400 font-medium">Step 4</span>
                  Iterate &amp; finalize
                </div>
              </div>
            </CardContent>
          </Card>
        )}

        <Card className="flex-1 flex flex-col overflow-hidden">
          <CardContent className="flex-1 overflow-y-auto p-4 space-y-3">
            {history.length === 0 && (
              <div className="text-muted-foreground text-sm text-center py-8 space-y-2">
                <p>Describe a chart pattern or upload a chart image / PDF / document.</p>
                <p className="text-xs">Supported: JPG &middot; PNG &middot; PDF &middot; DOCX &middot; TXT</p>
                <p className="text-xs opacity-60">
                  e.g. &quot;Flag pole breakout&quot; or upload a screenshot of a setup you like
                </p>
              </div>
            )}
            {history.map((msg, i) => (
              <ChatBubble key={i} msg={msg} />
            ))}
            {sending && (
              <div className="flex justify-start">
                <div className="bg-muted rounded-lg px-4 py-2 text-sm text-muted-foreground">
                  <span className="animate-pulse">Analyzing...</span>
                </div>
              </div>
            )}
            <div ref={bottomRef} />
          </CardContent>

          <Separator />
          <AttachmentStrip files={attachments} onRemove={removeAttachment} />

          <div className="p-3 flex gap-2 items-end">
            <input
              ref={fileInputRef}
              type="file"
              multiple
              accept={ACCEPT}
              className="hidden"
              onChange={(e) => {
                const selected = Array.from(e.target.files ?? []);
                const newAttachments: AttachedFile[] = selected.map((f) => ({
                  file: f,
                  preview: f.type.startsWith("image/") ? URL.createObjectURL(f) : null,
                }));
                setAttachments((prev) => [...prev, ...newAttachments].slice(0, 5));
                e.target.value = "";
              }}
            />
            <Button
              variant="outline"
              size="icon"
              className="shrink-0 h-9 w-9"
              onClick={() => fileInputRef.current?.click()}
              title="Attach chart image, PDF, or document"
            >
              <Paperclip className="h-4 w-4" />
            </Button>
            <Textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  send();
                }
              }}
              placeholder={
                attachments.length > 0
                  ? "Add a message (optional) or just send the file..."
                  : "Describe your pattern, or attach a chart image / PDF..."
              }
              rows={2}
              className="resize-none"
            />
            <Button
              onClick={send}
              disabled={sending || (!input.trim() && attachments.length === 0)}
              size="icon"
              className="shrink-0 h-9 w-9"
            >
              <Send className="h-4 w-4" />
            </Button>
          </div>
        </Card>
      </div>

      {/* Rulebook panel — always visible */}
      <div className="w-80 shrink-0">
        <Card className="h-full flex flex-col">
          <CardHeader className="pb-2 shrink-0">
            <CardTitle className="text-sm flex items-center gap-2">
              Rulebook
              {rulebookDraft ? (
                rulebookDraft.finalized ? (
                  <Badge className="bg-green-500/20 text-green-400 text-xs border-green-500/30">
                    Finalized
                  </Badge>
                ) : (
                  <Badge variant="outline" className="text-xs">
                    Draft
                  </Badge>
                )
              ) : (
                <Badge variant="outline" className="text-xs text-muted-foreground">
                  Empty
                </Badge>
              )}
            </CardTitle>
            {rulebookDraft && typeof rulebookDraft.description === "string" && (
              <p className="text-xs text-muted-foreground mt-1">{rulebookDraft.description}</p>
            )}
          </CardHeader>
          <CardContent className="flex-1 overflow-y-auto">
            {rulebookDraft ? (
              <RulebookPreview json={rulebookDraft} onEdit={handleRulebookEdit} />
            ) : (
              <p className="text-xs text-muted-foreground text-center py-8">
                No rulebook yet. Chat with the AI to define your pattern.
              </p>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

// ─── BACKTEST TAB ─────────────────────────────────────────────────────────────

function BacktestTab({
  patternId,
  runs,
  loadRuns,
}: {
  patternId: string;
  runs: BacktestRun[];
  loadRuns: () => void;
}) {
  const [running, setRunning] = useState(false);
  const [scanScope, setScanScope] = useState<"full" | "nifty50" | "custom">("nifty50");
  const [customSymbols, setCustomSymbols] = useState("");
  const [symbolBreakdown, setSymbolBreakdown] = useState<
    { symbol: string; count: number; success: number; failure: number }[]
  >([]);

  const latestRun = runs[0] ?? null;

  useEffect(() => {
    if (!patternId) return;
    // Compute symbol breakdown from events
    studioApi
      .getEvents(patternId, { limit: 200 })
      .then((res) => {
        const map: Record<string, { count: number; success: number; failure: number }> = {};
        for (const e of res.events) {
          if (!map[e.symbol]) map[e.symbol] = { count: 0, success: 0, failure: 0 };
          map[e.symbol].count++;
          if (e.outcome === "success") map[e.symbol].success++;
          if (e.outcome === "failure") map[e.symbol].failure++;
        }
        const sorted = Object.entries(map)
          .map(([symbol, v]) => ({ symbol, ...v }))
          .sort((a, b) => b.count - a.count)
          .slice(0, 10);
        setSymbolBreakdown(sorted);
      })
      .catch(() => {});
  }, [patternId, runs]);

  const handleRun = async () => {
    setRunning(true);
    try {
      // Prepare scan parameters based on selected scope
      const params: Record<string, string> = {};
      if (scanScope === "nifty50") {
        params.scope = "nifty50";
      } else if (scanScope === "custom" && customSymbols.trim()) {
        params.symbols = customSymbols.split(",").map(s => s.trim()).join(",");
      }
      // Pass parameters to backtest (backend will use defaults if not provided)
      await studioApi.runBacktest(patternId, params);
      toast.success("Backtest complete!");
      loadRuns();
    } catch (e) {
      toast.error(`Backtest failed: ${e instanceof Error ? e.message : "Unknown error"}`);
    } finally {
      setRunning(false);
    }
  };

  const totalForRate = latestRun
    ? (latestRun.success_count ?? 0) + (latestRun.failure_count ?? 0)
    : 0;

  return (
    <div className="space-y-4 overflow-y-auto flex-1">
      {/* Run controls */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm">Run Backtest</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <label className="text-xs font-medium text-muted-foreground">Scan Scope</label>
            <Select value={scanScope} onValueChange={(v) => setScanScope(v as any)}>
              <SelectTrigger className="text-xs">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="full">Full Universe (~326 stocks)</SelectItem>
                <SelectItem value="nifty50">Nifty 50 (50 stocks)</SelectItem>
                <SelectItem value="custom">Custom Symbols</SelectItem>
              </SelectContent>
            </Select>
            {scanScope === "custom" && (
              <Textarea
                placeholder="Enter comma-separated symbols (e.g., RELIANCE.NS, TCS.NS, INFY.NS)"
                value={customSymbols}
                onChange={(e) => setCustomSymbols(e.target.value)}
                className="text-xs h-20 resize-none"
              />
            )}
          </div>
          <p className="text-xs text-muted-foreground">
            {scanScope === "nifty50"
              ? "Scans 50 stocks (Nifty 50). Typically completes in ~10–20 seconds."
              : scanScope === "custom"
              ? "Scans your custom symbol list. Duration depends on count."
              : "Scans the full universe (~326 stocks). This can take 30–60 seconds."}
          </p>
          <div className="flex gap-2 w-full">
            <Button
              onClick={handleRun}
              disabled={running || (scanScope === "custom" && !customSymbols.trim())}
              className="gap-2 flex-1"
            >
              {running ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Running backtest...
                </>
              ) : (
                <>
                  <Play className="h-4 w-4" />
                  Run Backtest
                </>
              )}
            </Button>
            {running && (
              <Button
                onClick={() => setRunning(false)}
                variant="destructive"
                className="gap-2"
              >
                <X className="h-4 w-4" />
                Stop
              </Button>
            )}
          </div>
          {latestRun && (
            <div className="text-xs text-muted-foreground">
              Last run:{" "}
              {latestRun.started_at ? new Date(latestRun.started_at).toLocaleString() : "—"}
              {" · "}
              <span
                className={
                  latestRun.status === "complete"
                    ? "text-green-400"
                    : latestRun.status === "failed"
                    ? "text-red-400"
                    : "text-yellow-400"
                }
              >
                {latestRun.status}
              </span>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Performance summary */}
      {latestRun && latestRun.status === "complete" && (
        <>
          <div className="grid grid-cols-4 gap-3">
            {[
              {
                label: "Success Rate",
                value:
                  latestRun.success_rate != null ? `${latestRun.success_rate.toFixed(1)}%` : "—",
                color:
                  (latestRun.success_rate ?? 0) >= 50 ? "text-green-400" : "text-red-400",
              },
              {
                label: "Avg 10d Return",
                value: pct(latestRun.avg_ret_10d),
                color: pctColor(latestRun.avg_ret_10d),
              },
              {
                label: "Total Events",
                value: String(latestRun.events_found ?? 0),
                color: "text-foreground",
              },
              {
                label: "Symbols Scanned",
                value: String(latestRun.symbols_scanned ?? 0),
                color: "text-foreground",
              },
            ].map((card) => (
              <Card key={card.label}>
                <CardContent className="pt-4 pb-3 px-4">
                  <p className="text-xs text-muted-foreground mb-1">{card.label}</p>
                  <p className={`text-2xl font-bold ${card.color}`}>{card.value}</p>
                </CardContent>
              </Card>
            ))}
          </div>

          {/* Returns table */}
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm">Average Returns</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-3 gap-4 text-sm">
                {[
                  { label: "5d Return", value: latestRun.avg_ret_5d },
                  { label: "10d Return", value: latestRun.avg_ret_10d },
                  { label: "20d Return", value: latestRun.avg_ret_20d },
                ].map((r) => (
                  <div key={r.label} className="text-center">
                    <p className="text-xs text-muted-foreground">{r.label}</p>
                    <p className={`text-lg font-semibold ${pctColor(r.value)}`}>{pct(r.value)}</p>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>

          {/* Bar chart: Success / Failure / Neutral */}
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm">Outcome Distribution</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              {[
                { label: "Success", count: latestRun.success_count, color: "bg-green-500" },
                { label: "Failure", count: latestRun.failure_count, color: "bg-red-500" },
                { label: "Neutral", count: latestRun.neutral_count, color: "bg-gray-500" },
              ].map(({ label, count, color }) => {
                const pctVal = totalForRate > 0 ? (count / latestRun.events_found) * 100 : 0;
                return (
                  <div key={label} className="flex items-center gap-3">
                    <span className="text-xs text-muted-foreground w-14">{label}</span>
                    <div className="flex-1 bg-muted rounded-full h-2">
                      <div
                        className={`${color} h-2 rounded-full transition-all`}
                        style={{ width: `${pctVal}%` }}
                      />
                    </div>
                    <span className="text-xs text-muted-foreground w-12 text-right">
                      {count} ({pctVal.toFixed(0)}%)
                    </span>
                  </div>
                );
              })}
            </CardContent>
          </Card>

          {/* Symbol breakdown */}
          {symbolBreakdown.length > 0 && (
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm">Top Symbols by Events</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-1">
                  {symbolBreakdown.map((row) => {
                    const sr =
                      row.success + row.failure > 0
                        ? ((row.success / (row.success + row.failure)) * 100).toFixed(0)
                        : "—";
                    return (
                      <div
                        key={row.symbol}
                        className="flex items-center justify-between text-xs py-1 border-b border-border/50 last:border-0"
                      >
                        <span className="font-mono font-medium">{row.symbol}</span>
                        <span className="text-muted-foreground">{row.count} events</span>
                        <span className={sr !== "—" && Number(sr) >= 50 ? "text-green-400" : "text-red-400"}>
                          {sr}% win
                        </span>
                      </div>
                    );
                  })}
                </div>
              </CardContent>
            </Card>
          )}

          {/* Detailed Results */}
          <BacktestResults
            patternId={patternId}
            run={latestRun}
            onEventFeedback={(id, feedback, notes) => {
              // Optional: handle feedback updates
            }}
          />
        </>
      )}
    </div>
  );
}

// ─── EVENT CARD ───────────────────────────────────────────────────────────────

function EventCard({
  event,
  onFeedback,
}: {
  event: PatternEvent;
  onFeedback: (id: string, feedback: string, notes: string) => void;
}) {
  const [notes, setNotes] = useState(event.user_notes ?? "");
  const [expanded, setExpanded] = useState(false);

  const handleFeedback = (fb: string) => {
    onFeedback(event.id, fb, notes);
  };

  const handleNotesBlur = () => {
    if (notes !== (event.user_notes ?? "")) {
      onFeedback(event.id, event.user_feedback ?? "", notes);
    }
  };

  return (
    <Card className="border-border/60">
      <CardContent className="p-4 space-y-3">
        {/* Header row */}
        <div className="flex items-start justify-between gap-2">
          <div>
            <span className="font-mono font-semibold text-sm">{event.symbol}</span>
            <span className="text-xs text-muted-foreground ml-2">{event.detected_at}</span>
            {event.entry_price != null && (
              <span className="text-xs text-muted-foreground ml-2">
                @ {event.entry_price.toFixed(2)}
              </span>
            )}
          </div>
          <OutcomeBadge outcome={event.outcome} />
        </div>

        {/* Returns row */}
        <div className="grid grid-cols-5 gap-2 text-xs">
          {[
            { label: "5d", value: event.ret_5d },
            { label: "10d", value: event.ret_10d },
            { label: "20d", value: event.ret_20d },
            { label: "Max+", value: event.max_gain_20d },
            { label: "Max−", value: event.max_loss_20d, invert: true },
          ].map(({ label, value, invert }) => (
            <div key={label} className="text-center">
              <p className="text-muted-foreground">{label}</p>
              <p className={`font-medium ${pctColor(value, invert)}`}>{pct(value, 1)}</p>
            </div>
          ))}
        </div>

        {/* Indicators */}
        {event.indicator_snapshot && Object.keys(event.indicator_snapshot).length > 0 && (
          <div className="flex flex-wrap gap-2 text-xs">
            {Object.entries(event.indicator_snapshot)
              .slice(0, 5)
              .map(([k, v]) => (
                <span key={k} className="bg-muted px-2 py-0.5 rounded text-muted-foreground font-mono">
                  {k}: {v.toFixed(2)}
                </span>
              ))}
          </div>
        )}

        {/* Actions row */}
        <div className="flex items-center gap-2 flex-wrap">
          {/* Feedback buttons */}
          {(["valid", "invalid", "unsure"] as const).map((fb) => (
            <button
              key={fb}
              onClick={() => handleFeedback(fb)}
              className={`text-xs px-2 py-1 rounded border transition-colors ${
                event.user_feedback === fb
                  ? fb === "valid"
                    ? "bg-green-500/20 border-green-500/40 text-green-400"
                    : fb === "invalid"
                    ? "bg-red-500/20 border-red-500/40 text-red-400"
                    : "bg-yellow-500/20 border-yellow-500/40 text-yellow-400"
                  : "border-border text-muted-foreground hover:border-foreground/40"
              }`}
            >
              {fb === "valid" ? "✓ Valid" : fb === "invalid" ? "✗ Invalid" : "? Unsure"}
            </button>
          ))}

          {/* View on Chart */}
          <button
            onClick={() =>
              window.open(`/chart?symbol=${event.symbol}`, "_blank")
            }
            className="ml-auto flex items-center gap-1 text-xs text-blue-400 hover:text-blue-300"
          >
            <ExternalLink className="h-3 w-3" />
            View Chart
          </button>

          {/* Notes toggle */}
          <button
            onClick={() => setExpanded((o) => !o)}
            className="text-xs text-muted-foreground hover:text-foreground"
          >
            {expanded ? "Hide notes ▲" : "Add notes ▼"}
          </button>
        </div>

        {expanded && (
          <textarea
            className="w-full h-16 text-xs bg-muted/40 border border-border rounded p-2 text-foreground resize-none focus:outline-none"
            placeholder="Add notes about this event..."
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            onBlur={handleNotesBlur}
          />
        )}
      </CardContent>
    </Card>
  );
}

// ─── EVENTS TAB ───────────────────────────────────────────────────────────────

function EventsTab({ patternId }: { patternId: string }) {
  const [events, setEvents] = useState<PatternEvent[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [offset, setOffset] = useState(0);
  const [symbolFilter, setSymbolFilter] = useState("");
  const [outcomeFilter, setOutcomeFilter] = useState("all");
  const [feedbackFilter, setFeedbackFilter] = useState("all");

  const LIMIT = 50;

  const loadEvents = useCallback(
    async (reset = false) => {
      if (!patternId) return;
      setLoading(true);
      const newOffset = reset ? 0 : offset;
      try {
        const params: { symbol?: string; outcome?: string; limit: number; offset: number } = {
          limit: LIMIT,
          offset: newOffset,
        };
        if (symbolFilter.trim()) params.symbol = symbolFilter.trim().toUpperCase();
        if (outcomeFilter !== "all") params.outcome = outcomeFilter;
        const res = await studioApi.getEvents(patternId, params);
        if (reset) {
          setEvents(res.events);
          setOffset(LIMIT);
        } else {
          setEvents((prev) => [...prev, ...res.events]);
          setOffset(newOffset + LIMIT);
        }
        setTotal(res.total);
      } catch {
        toast.error("Failed to load events");
      } finally {
        setLoading(false);
      }
    },
    [patternId, symbolFilter, outcomeFilter, offset]
  );

  useEffect(() => {
    loadEvents(true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [patternId, symbolFilter, outcomeFilter]);

  const handleFeedback = async (id: string, feedback: string, notes: string) => {
    await studioApi.updateEventFeedback(id, feedback, notes);
    setEvents((prev) =>
      prev.map((e) => (e.id === id ? { ...e, user_feedback: feedback, user_notes: notes } : e))
    );
  };

  // Client-side feedback filter
  const filtered =
    feedbackFilter === "all"
      ? events
      : feedbackFilter === "unreviewed"
      ? events.filter((e) => !e.user_feedback)
      : events.filter((e) => e.user_feedback === feedbackFilter);

  return (
    <div className="flex flex-col gap-3 flex-1 min-h-0">
      {/* Filters */}
      <div className="flex flex-wrap gap-2 items-center">
        <input
          type="text"
          placeholder="Symbol search..."
          value={symbolFilter}
          onChange={(e) => setSymbolFilter(e.target.value)}
          className="h-8 rounded-md border border-border bg-muted px-3 text-xs w-36 focus:outline-none"
        />

        <Select value={outcomeFilter} onValueChange={(v) => { if (v) setOutcomeFilter(v); }}>
          <SelectTrigger className="h-8 w-36 text-xs">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {["all", "success", "failure", "neutral", "pending"].map((v) => (
              <SelectItem key={v} value={v} className="text-xs capitalize">
                {v === "all" ? "All outcomes" : v}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        <Select value={feedbackFilter} onValueChange={(v) => { if (v) setFeedbackFilter(v); }}>
          <SelectTrigger className="h-8 w-36 text-xs">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {["all", "valid", "invalid", "unsure", "unreviewed"].map((v) => (
              <SelectItem key={v} value={v} className="text-xs capitalize">
                {v === "all" ? "All feedback" : v}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        <span className="text-xs text-muted-foreground ml-auto">
          {filtered.length} / {total} events
        </span>
      </div>

      {/* Event list */}
      <div className="overflow-y-auto flex-1 space-y-2">
        {loading && filtered.length === 0 && (
          <div className="text-center py-8">
            <Loader2 className="h-5 w-5 animate-spin mx-auto text-muted-foreground" />
          </div>
        )}
        {!loading && filtered.length === 0 && (
          <div className="text-center text-muted-foreground text-sm py-8">
            No events found. Run a backtest first.
          </div>
        )}
        {filtered.map((e) => (
          <EventCard key={e.id} event={e} onFeedback={handleFeedback} />
        ))}
        {events.length < total && (
          <Button
            variant="outline"
            className="w-full text-xs"
            onClick={() => loadEvents(false)}
            disabled={loading}
          >
            {loading ? "Loading..." : `Load more (${total - events.length} remaining)`}
          </Button>
        )}
      </div>
    </div>
  );
}

// ─── STUDY TAB ────────────────────────────────────────────────────────────────

function StudyTab({ patternId }: { patternId: string }) {
  const [study, setStudy] = useState<PatternStudyResult | null>(null);
  const [generating, setGenerating] = useState(false);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    if (!patternId) return;
    studioApi
      .getLatestStudy(patternId)
      .then((s) => {
        setStudy(s);
        setLoaded(true);
      })
      .catch(() => setLoaded(true));
  }, [patternId]);

  const handleGenerate = async () => {
    setGenerating(true);
    try {
      const result = await studioApi.generateStudy(patternId);
      setStudy(result);
      toast.success("Study generated!");
    } catch (e) {
      toast.error(`Study failed: ${e instanceof Error ? e.message : "Unknown error"}`);
    } finally {
      setGenerating(false);
    }
  };

  return (
    <div className="flex flex-col gap-4 overflow-y-auto flex-1">
      {/* Header controls */}
      <Card>
        <CardContent className="p-4 flex items-center justify-between gap-4">
          <div>
            <p className="text-sm font-medium">Pattern Intelligence Study</p>
            <p className="text-xs text-muted-foreground mt-0.5">
              LLM analysis of backtest results — success factors, failure modes, rulebook improvements.
            </p>
            {study?.created_at && (
              <p className="text-xs text-muted-foreground mt-1">
                Last generated: {new Date(study.created_at).toLocaleString()}
              </p>
            )}
          </div>
          <Button onClick={handleGenerate} disabled={generating} className="shrink-0 gap-2">
            {generating ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" />
                Generating...
              </>
            ) : (
              <>
                <RefreshCw className="h-4 w-4" />
                {study ? "Regenerate Study" : "Generate Study"}
              </>
            )}
          </Button>
        </CardContent>
      </Card>

      {!loaded && (
        <div className="text-center py-8">
          <Loader2 className="h-5 w-5 animate-spin mx-auto text-muted-foreground" />
        </div>
      )}

      {loaded && !study && !generating && (
        <div className="text-center text-muted-foreground text-sm py-8">
          No study yet. Run a backtest first, then generate a study.
        </div>
      )}

      {study && (
        <>
          {/* Narrative analysis */}
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm">Analysis</CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-sm text-foreground/90 leading-relaxed whitespace-pre-wrap">
                {study.analysis}
              </p>
            </CardContent>
          </Card>

          <div className="grid grid-cols-2 gap-4">
            {/* Success factors */}
            {study.success_factors && study.success_factors.length > 0 && (
              <Card className="border-green-500/20">
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm text-green-400">Success Factors</CardTitle>
                </CardHeader>
                <CardContent>
                  <ul className="space-y-1.5">
                    {study.success_factors.map((f, i) => (
                      <li key={i} className="text-xs text-foreground/80 flex gap-2">
                        <span className="text-green-400 shrink-0">+</span>
                        {f}
                      </li>
                    ))}
                  </ul>
                </CardContent>
              </Card>
            )}

            {/* Failure factors */}
            {study.failure_factors && study.failure_factors.length > 0 && (
              <Card className="border-red-500/20">
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm text-red-400">Failure Factors</CardTitle>
                </CardHeader>
                <CardContent>
                  <ul className="space-y-1.5">
                    {study.failure_factors.map((f, i) => (
                      <li key={i} className="text-xs text-foreground/80 flex gap-2">
                        <span className="text-red-400 shrink-0">−</span>
                        {f}
                      </li>
                    ))}
                  </ul>
                </CardContent>
              </Card>
            )}
          </div>

          {/* Rulebook suggestions */}
          {study.rulebook_suggestions && study.rulebook_suggestions.length > 0 && (
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm">Rulebook Suggestions</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                {study.rulebook_suggestions.map((s, i) => (
                  <div key={i} className="border border-border rounded-md p-3 space-y-1">
                    <div className="flex items-center gap-2">
                      <Badge variant="outline" className="text-xs font-mono">
                        {s.type}
                      </Badge>
                      <span className="text-xs text-foreground/80">{s.condition}</span>
                    </div>
                    <p className="text-xs text-muted-foreground">{s.rationale}</p>
                  </div>
                ))}
              </CardContent>
            </Card>
          )}

          {/* Confidence improvements */}
          {study.confidence_improvements && study.confidence_improvements.length > 0 && (
            <Card className="border-amber-500/20">
              <CardHeader className="pb-2">
                <CardTitle className="text-sm text-amber-400">Confidence Improvements</CardTitle>
              </CardHeader>
              <CardContent>
                <ul className="space-y-1.5">
                  {study.confidence_improvements.map((c, i) => (
                    <li key={i} className="text-xs text-foreground/80 flex gap-2">
                      <span className="text-amber-400 shrink-0">~</span>
                      {c}
                    </li>
                  ))}
                </ul>
              </CardContent>
            </Card>
          )}
        </>
      )}
    </div>
  );
}

// ─── MAIN PAGE ────────────────────────────────────────────────────────────────

export default function StudioPage() {
  const [patterns, setPatterns] = useState<Pattern[]>([]);
  const [selectedId, setSelectedId] = useState<string>("new");
  const [history, setHistory] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [attachments, setAttachments] = useState<AttachedFile[]>([]);
  const [sending, setSending] = useState(false);
  const [scanning, setScanning] = useState(false);
  const [currentPatternId, setCurrentPatternId] = useState<string | null>(null);
  const [rulebookDraft, setRulebookDraft] = useState<Record<string, unknown> | null>(null);
  const [activeTab, setActiveTab] = useState<ActiveTab>("define");
  const [backtestRuns, setBacktestRuns] = useState<BacktestRun[]>([]);

  const fileInputRef = useRef<HTMLInputElement>(null);

  const loadPatterns = () => patternsApi.list().then(setPatterns);

  const loadBacktestRuns = useCallback(() => {
    if (!currentPatternId) return;
    studioApi
      .getBacktestRuns(currentPatternId)
      .then(setBacktestRuns)
      .catch(() => {});
  }, [currentPatternId]);

  useEffect(() => {
    loadPatterns();
  }, []);

  useEffect(() => {
    if (selectedId && selectedId !== "new") {
      setCurrentPatternId(selectedId);
      fetch(`${BASE}/studio/${selectedId}/history`)
        .then((r) => r.json())
        .then(setHistory)
        .catch(() => {});
    } else {
      setHistory([]);
      setCurrentPatternId(null);
    }
    setRulebookDraft(null);
    setAttachments([]);
    setBacktestRuns([]);
  }, [selectedId]);

  useEffect(() => {
    loadBacktestRuns();
  }, [loadBacktestRuns]);

  // ── Send message ────────────────────────────────────────────────────────────
  const send = async () => {
    if (!input.trim() && attachments.length === 0) return;
    if (sending) return;

    const userDisplayContent =
      attachments.length > 0
        ? `[Attached: ${attachments.map((a) => a.file.name).join(", ")}]\n${input}`.trim()
        : input.trim();

    setHistory((h) => [...h, { role: "user", content: userDisplayContent }]);
    const savedInput = input;
    const savedAttachments = [...attachments];
    setInput("");
    setAttachments([]);
    setSending(true);

    try {
      let res: ChatResponse;

      if (savedAttachments.length > 0) {
        const fd = new FormData();
        fd.append("message", savedInput);
        if (currentPatternId) fd.append("pattern_id", currentPatternId);
        savedAttachments.forEach((a) => fd.append("files", a.file));

        const resp = await fetch(`${BASE}/studio/chat-with-files`, {
          method: "POST",
          body: fd,
        });
        if (!resp.ok) throw new Error(await resp.text());
        res = await resp.json();
      } else {
        const resp = await fetch(`${BASE}/studio/chat`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            pattern_id: currentPatternId ?? undefined,
            message: savedInput,
          }),
        });
        if (!resp.ok) throw new Error(await resp.text());
        res = await resp.json();
      }

      setCurrentPatternId(res.pattern_id);
      setHistory((h) => [...h, { role: "assistant", content: res.reply }]);

      if (res.rulebook_draft) {
        setRulebookDraft(res.rulebook_draft);
        if (res.rulebook_draft.finalized) {
          toast.success("Rulebook finalized and saved!");
          loadPatterns();
        }
      }
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Unknown error";
      toast.error(`Failed: ${msg.slice(0, 120)}`);
      setHistory((h) => h.slice(0, -1));
    } finally {
      setSending(false);
      savedAttachments.forEach((a) => {
        if (a.preview) URL.revokeObjectURL(a.preview);
      });
    }
  };

  const runScan = async () => {
    if (!currentPatternId) return;
    setScanning(true);
    try {
      // Scan using nifty50 by default (consistent with backtest default)
      const res = await scannerApi.run(currentPatternId, undefined, "nifty50");
      toast.success(
        `Scan complete: ${res.signals_created} signals from ${res.symbols_scanned} Nifty 50 symbols in ${res.duration_seconds}s`
      );
    } catch {
      toast.error("Scan failed");
    } finally {
      setScanning(false);
    }
  };

  const handleRulebookEdit = (raw: string) => {
    try {
      setRulebookDraft(JSON.parse(raw));
    } catch {
      /* ignore */
    }
  };

  const selectedPattern = patterns.find((p) => p.id === selectedId);

  const TABS: { id: ActiveTab; label: string; icon: React.ReactNode; requiresPattern: boolean }[] = [
    { id: "define", label: "Define", icon: <MessageSquare className="h-3.5 w-3.5" />, requiresPattern: false },
    { id: "backtest", label: "Backtest", icon: <BarChart2 className="h-3.5 w-3.5" />, requiresPattern: true },
    { id: "events", label: "Events", icon: <List className="h-3.5 w-3.5" />, requiresPattern: true },
    { id: "study", label: "Study", icon: <BookOpen className="h-3.5 w-3.5" />, requiresPattern: true },
  ];

  return (
    <div className="flex flex-col gap-3 h-[calc(100vh-5rem)] max-w-7xl">
      {/* Top bar */}
      <div className="flex items-center gap-3 shrink-0">
        <h1 className="text-2xl font-bold">Pattern Studio</h1>
        {currentPatternId && selectedPattern && (
          <Badge
            variant={selectedPattern.status === "active" ? "default" : "secondary"}
          >
            {selectedPattern.status}
          </Badge>
        )}

        <Select
          value={selectedId}
          onValueChange={(v) => {
            if (v) {
              setSelectedId(v);
              setActiveTab("define");
            }
          }}
        >
          <SelectTrigger className="w-64 ml-2">
            <SelectValue placeholder="Select pattern or start new..." />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="new">
              <span className="flex items-center gap-1">
                <Plus className="h-3 w-3" /> New Pattern
              </span>
            </SelectItem>
            {patterns.map((p) => (
              <SelectItem key={p.id} value={p.id}>
                {p.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        {currentPatternId && (
          <Button size="sm" variant="outline" onClick={runScan} disabled={scanning}>
            <Play className="h-3 w-3 mr-1" />
            {scanning ? "Scanning..." : "Run Scan"}
          </Button>
        )}
      </div>

      {/* Tab bar */}
      <div className="flex gap-1 shrink-0 border-b border-border pb-0">
        {TABS.map((tab) => {
          const disabled = tab.requiresPattern && !currentPatternId;
          return (
            <button
              key={tab.id}
              disabled={disabled}
              onClick={() => !disabled && setActiveTab(tab.id)}
              className={`flex items-center gap-1.5 px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
                activeTab === tab.id
                  ? "border-primary text-foreground"
                  : "border-transparent text-muted-foreground hover:text-foreground"
              } ${disabled ? "opacity-40 cursor-not-allowed" : "cursor-pointer"}`}
            >
              {tab.icon}
              {tab.label}
            </button>
          );
        })}
      </div>

      {/* Tab content */}
      <div className="flex-1 min-h-0 overflow-hidden flex flex-col">
        {activeTab === "define" && (
          <DefineTab
            history={history}
            sending={sending}
            rulebookDraft={rulebookDraft}
            attachments={attachments}
            input={input}
            setInput={setInput}
            setAttachments={setAttachments}
            send={send}
            handleRulebookEdit={handleRulebookEdit}
            fileInputRef={fileInputRef}
          />
        )}

        {activeTab === "backtest" && currentPatternId && (
          <BacktestTab
            patternId={currentPatternId}
            runs={backtestRuns}
            loadRuns={loadBacktestRuns}
          />
        )}

        {activeTab === "events" && currentPatternId && (
          <EventsTab patternId={currentPatternId} />
        )}

        {activeTab === "study" && currentPatternId && (
          <StudyTab patternId={currentPatternId} />
        )}
      </div>
    </div>
  );
}
