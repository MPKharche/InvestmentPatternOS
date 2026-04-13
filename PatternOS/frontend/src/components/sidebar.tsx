"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  BarChart3,
  BookOpen,
  CandlestickChart,
  Globe,
  LayoutDashboard,
  Radio,
  Sparkles,
} from "lucide-react";
import { cn } from "@/lib/utils";

const nav = [
  { href: "/",          label: "Dashboard",      icon: LayoutDashboard },
  { href: "/signals",   label: "Signal Inbox",   icon: Radio },
  { href: "/studio",    label: "Pattern Studio", icon: Sparkles },
  { href: "/chart",     label: "Chart Tool",     icon: CandlestickChart },
  { href: "/journal",   label: "Trade Journal",  icon: BookOpen },
  { href: "/analytics", label: "Analytics",      icon: BarChart3 },
  { href: "/universe",  label: "Universe",       icon: Globe },
];

export function Sidebar() {
  const pathname = usePathname();
  return (
    <aside className="w-56 shrink-0 border-r border-border bg-card flex flex-col py-4 gap-1">
      <div className="px-4 mb-4">
        <span className="text-lg font-bold tracking-tight text-primary">PatternOS</span>
      </div>
      {nav.map(({ href, label, icon: Icon }) => (
        <Link
          key={href}
          href={href}
          className={cn(
            "flex items-center gap-3 px-4 py-2 text-sm rounded-md mx-2 transition-colors",
            pathname === href
              ? "bg-primary/10 text-primary font-medium"
              : "text-muted-foreground hover:text-foreground hover:bg-accent"
          )}
        >
          <Icon className="h-4 w-4" />
          {label}
        </Link>
      ))}
    </aside>
  );
}
