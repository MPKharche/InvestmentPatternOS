"use client";

import { useEffect, useMemo, useState } from "react";
import { Sidebar } from "@/components/sidebar";
import { Button } from "@/components/ui/button";
import { Menu } from "lucide-react";
import { SystemOfflineBanner, SystemStatusPill } from "@/components/system-status";

export function Shell({ children }: { children: React.ReactNode }) {
  const [mobileOpen, setMobileOpen] = useState(false);

  // Close mobile drawer when resizing up to desktop.
  useEffect(() => {
    const onResize = () => {
      if (window.innerWidth >= 768) setMobileOpen(false);
    };
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);

  const topbar = useMemo(() => {
    return (
      <div className="md:hidden sticky top-0 z-40 border-b border-border bg-background/80 backdrop-blur">
        <div className="h-12 px-3 flex items-center gap-2">
          <Button
            size="icon"
            variant="ghost"
            className="h-9 w-9"
            onClick={() => setMobileOpen(true)}
            title="Open menu"
          >
            <Menu className="h-4 w-4" />
          </Button>
          <span className="text-sm font-semibold tracking-tight">PatternOS</span>
          <div className="ml-auto">
            <SystemStatusPill />
          </div>
        </div>
      </div>
    );
  }, []);

  return (
    <div className="flex h-screen overflow-hidden">
      <Sidebar mobileOpen={mobileOpen} onMobileClose={() => setMobileOpen(false)} />
      <div className="flex-1 min-w-0 flex flex-col">
        {topbar}
        <main className="flex-1 overflow-y-auto p-4 md:p-6">
          <div className="hidden md:flex items-center justify-end mb-4">
            <SystemStatusPill />
          </div>
          <SystemOfflineBanner />
          {children}
        </main>
      </div>
    </div>
  );
}
