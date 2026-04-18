"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  BarChart3,
  BookOpen,
  CandlestickChart,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  Globe,
  LayoutDashboard,
  Radio,
  Sparkles,
  Activity,
  LineChart,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { useEffect, useMemo, useState } from "react";

type NavItem = { href: string; label: string; icon: React.ElementType };
type NavGroup = { key: "equity" | "mf"; label: string; items: NavItem[] };

const GROUPS: NavGroup[] = [
  {
    key: "equity",
    label: "Equity",
    items: [
      { href: "/", label: "Dashboard", icon: LayoutDashboard },
      { href: "/signals", label: "Signal Inbox", icon: Radio },
      { href: "/studio", label: "Pattern Studio", icon: Sparkles },
      { href: "/chart", label: "Chart Tool", icon: CandlestickChart },
      { href: "/journal", label: "Trade Journal", icon: BookOpen },
      { href: "/analytics", label: "Analytics", icon: BarChart3 },
      { href: "/universe", label: "Universe", icon: Globe },
      { href: "/status", label: "System Status", icon: Activity },
    ],
  },
  {
    key: "mf",
    label: "Mutual Funds",
    items: [
      { href: "/mf", label: "Dashboard", icon: LayoutDashboard },
      { href: "/mf/chart", label: "Chart Tool", icon: LineChart },
      { href: "/mf/schemes", label: "Schemes", icon: Globe },
      { href: "/mf/signals", label: "Signals", icon: Radio },
      { href: "/mf/rulebooks", label: "Rulebooks", icon: Sparkles },
      { href: "/mf/pipelines", label: "Pipelines", icon: BarChart3 },
    ],
  },
];

function readBool(key: string, fallback: boolean) {
  if (typeof window === "undefined") return fallback;
  const raw = window.localStorage.getItem(key);
  if (raw === null) return fallback;
  return raw === "true";
}

function writeBool(key: string, v: boolean) {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(key, v ? "true" : "false");
}

export function Sidebar({
  mobileOpen,
  onMobileClose,
}: {
  mobileOpen: boolean;
  onMobileClose: () => void;
}) {
  const pathname = usePathname();
  const [collapsed, setCollapsed] = useState(false);
  const [equityOpen, setEquityOpen] = useState(true);
  const [mfOpen, setMfOpen] = useState(false);

  useEffect(() => {
    setCollapsed(readBool("sidebar_collapsed", false));
    setEquityOpen(readBool("nav_group_equity_open", true));
    setMfOpen(readBool("nav_group_mf_open", false));
  }, []);

  useEffect(() => writeBool("sidebar_collapsed", collapsed), [collapsed]);
  useEffect(() => writeBool("nav_group_equity_open", equityOpen), [equityOpen]);
  useEffect(() => writeBool("nav_group_mf_open", mfOpen), [mfOpen]);

  const groupsState = useMemo(() => {
    return {
      equity: { open: equityOpen, setOpen: setEquityOpen },
      mf: { open: mfOpen, setOpen: setMfOpen },
    } as const;
  }, [equityOpen, mfOpen]);

  const content = (
    <aside
      className={cn(
        "shrink-0 border-r border-border bg-card flex flex-col py-4 gap-2 h-full",
        collapsed ? "w-[60px]" : "w-60"
      )}
    >
      <div className={cn("px-3 flex items-center gap-2", collapsed ? "justify-center" : "")}>
        {!collapsed && (
          <span className="text-lg font-bold tracking-tight text-primary">PatternOS</span>
        )}
        <Button
          size="icon-sm"
          variant="ghost"
          className={cn("ml-auto", collapsed ? "ml-0" : "")}
          onClick={() => setCollapsed((v) => !v)}
          title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
        >
          {collapsed ? <ChevronRight className="h-4 w-4" /> : <ChevronLeft className="h-4 w-4" />}
        </Button>
      </div>

      <div className="px-2 flex-1 overflow-y-auto">
        {GROUPS.map((g) => {
          const st = groupsState[g.key];
          const isOpen = collapsed ? true : st.open;
          return (
            <div key={g.key} className="mb-2">
              <button
                type="button"
                className={cn(
                  "w-full flex items-center gap-2 px-2 py-2 rounded-md text-xs font-semibold tracking-wide text-muted-foreground hover:text-foreground hover:bg-accent transition-colors",
                  collapsed ? "justify-center" : ""
                )}
                onClick={() => {
                  if (collapsed) return;
                  st.setOpen(!st.open);
                }}
                title={collapsed ? g.label : undefined}
              >
                {!collapsed && <span className="uppercase">{g.label}</span>}
                {!collapsed && (
                  <ChevronDown className={cn("h-4 w-4 ml-auto transition-transform", st.open ? "rotate-180" : "")} />
                )}
              </button>

              {isOpen && (
                <div className="mt-1 flex flex-col gap-1">
                  {g.items.map(({ href, label, icon: Icon }) => (
                    <Link
                      key={href}
                      href={href}
                      onClick={() => onMobileClose()}
                      title={collapsed ? label : undefined}
                      className={cn(
                        "flex items-center gap-3 px-3 py-2 text-sm rounded-md mx-1 transition-colors",
                        collapsed ? "justify-center px-0" : "",
                        pathname === href
                          ? "bg-primary/10 text-primary font-medium"
                          : "text-muted-foreground hover:text-foreground hover:bg-accent"
                      )}
                    >
                      <Icon className="h-4 w-4" />
                      {!collapsed && <span className="truncate">{label}</span>}
                    </Link>
                  ))}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </aside>
  );

  return (
    <>
      {/* Desktop */}
      <div className="hidden md:block">{content}</div>

      {/* Mobile overlay */}
      {mobileOpen && (
        <div className="md:hidden fixed inset-0 z-50">
          <div
            className="absolute inset-0 bg-black/50"
            onClick={onMobileClose}
            aria-hidden="true"
          />
          <div className="absolute inset-y-0 left-0">{content}</div>
        </div>
      )}
    </>
  );
}
