import { useState } from "react";
import { Outlet } from "react-router-dom";
import { Sidebar } from "@/components/Sidebar";
import { Topbar } from "@/components/Topbar";
import { AskAspora } from "@/components/AskAspora";
import { ObligationDrawer } from "@/components/ObligationDrawer";
import { cn } from "@/lib/utils";

export function AppShell() {
  const [collapsed, setCollapsed] = useState(false);

  return (
    <div className="flex h-full bg-secondary/40">
      <Sidebar collapsed={collapsed} onToggle={() => setCollapsed((c) => !c)} />
      <div className={cn("flex-1 flex flex-col min-w-0")}>
        <Topbar />
        <main className="flex-1 overflow-auto scrollbar-thin">
          <div className="px-8 py-6 max-w-[1500px] mx-auto">
            <Outlet />
          </div>
        </main>
      </div>
      <ObligationDrawer />
      <AskAspora />
    </div>
  );
}
