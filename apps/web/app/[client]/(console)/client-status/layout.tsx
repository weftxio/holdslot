"use client";
import { useContext } from "react";
import { createPortal } from "react-dom";
import { usePathname, useRouter } from "next/navigation";
import clsx from "clsx";
import { useClient } from "@/lib/nav";
import { TopbarSlotCtx } from "@/components/console/ConsoleShell";
import { STATUS_TABS, type StatusTabKey } from "@/components/console/StatusTab";
import "./client-status.css";

// The three Client Action tabs are real nested routes (approval/booking/feedback). This layout
// persists across sub-route navigation, so its tab bar stays mounted (no remount flicker) and is
// portaled into the console topbar (replacing the breadcrumb). The active tab is derived from the
// URL — no shared context needed. Tabs stay <button>s (not <Link>s) so the `.tab` styling is
// byte-identical to the design; navigation is via router.push so each tab is a history entry.
export default function ClientStatusLayout({ children }: { children: React.ReactNode }) {
  const client = useClient();
  const pathname = usePathname();
  const router = useRouter();
  const active = (pathname.split("/")[3] || "approval") as StatusTabKey;
  const tabSlot = useContext(TopbarSlotCtx);

  const tabBar = (
    <div className="tabs" role="tablist">
      {STATUS_TABS.map(([k, label]) => (
        <button
          key={k}
          className={clsx("tab", active === k && "active")}
          onClick={() => router.push(`/${client}/client-status/${k}`)}
        >
          {label}
        </button>
      ))}
    </div>
  );

  return (
    <>
      {tabSlot ? createPortal(tabBar, tabSlot) : tabBar}
      {children}
    </>
  );
}
