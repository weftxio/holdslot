"use client";
import { useContext } from "react";
import { createPortal } from "react-dom";
import { usePathname, useRouter } from "next/navigation";
import clsx from "clsx";
import { useClient } from "@/lib/nav";
import { TopbarSlotCtx } from "@/components/console/ConsoleShell";
import { WorkspaceProvider, useWorkspace } from "@/components/workspace/WorkspaceProvider";
import { TABS } from "@/lib/workspace/constants";
import "./workspace.css";

// The seven workspace tabs are real nested routes (brief/list/batches/campaign/replies/summaries/
// billing). This layout persists across sub-route navigation, so its tab bar stays mounted (no
// remount flicker) and is portaled into the console topbar (replacing the breadcrumb). Tabs stay
// <button>s (not <Link>s) so the `.tab` styling is byte-identical to the design; navigation is via
// router.push so each tab is a history entry. The count pips read the cross-tab state that lives in
// WorkspaceProvider, so the tab bar is rendered inside it (WorkspaceTabBar).
function WorkspaceTabBar() {
  const client = useClient();
  const pathname = usePathname();
  const router = useRouter();
  const tabSlot = useContext(TopbarSlotCtx);
  const { batches, campaigns, replies } = useWorkspace();
  const active = pathname.split("/")[3] || "brief";
  const remaining = replies.filter((r) => !r.done).length;

  const tabBar = (
    <div className="tabs ws-tabs" role="tablist">
      {TABS.map(([k, label]) => (
        <button
          key={k}
          className={clsx("tab", active === k && "active")}
          onClick={() => router.push(`/${client}/workspace/${k}`)}
        >
          {label}
          {k === "batches" && <span className="cnt">{batches.length}</span>}
          {k === "campaign" && <span className="cnt">{campaigns.length}</span>}
          {k === "replies" && (
            <span className={clsx("cnt", remaining > 0 && "alert")}>{remaining}</span>
          )}
        </button>
      ))}
    </div>
  );

  return tabSlot ? createPortal(tabBar, tabSlot) : tabBar;
}

export default function WorkspaceLayout({ children }: { children: React.ReactNode }) {
  return (
    <WorkspaceProvider>
      <WorkspaceTabBar />
      {children}
    </WorkspaceProvider>
  );
}
