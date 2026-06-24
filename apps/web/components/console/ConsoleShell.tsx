"use client";
import { createContext, useState } from "react";
import { usePathname } from "next/navigation";
import Link from "next/link";
import { Sidebar } from "./Sidebar";
import { MeProvider } from "./MeContext";
import { SessionGuard } from "./SessionGuard";
import { ToastProvider } from "../Toast";
import { slugToTitle } from "@/lib/client";
import { STATUS_LABEL, STATUS_BACK, type StatusTabKey } from "./StatusTab";
import "./console-shell.css";

const LABELS: Record<string, string> = {
  "performance-summary": "Performance Summary",
  workspace: "Workspace",
  "client-status": "Client Action",
};

// The workspace page lifts its tab bar into the topbar (replacing the breadcrumb) so the full
// main pane is content. ConsoleShell renders the empty slot element here; the page portals its
// stateful tab bar into it via this context.
export const TopbarSlotCtx = createContext<HTMLElement | null>(null);

export function ConsoleShell({ slug, children }: { slug: string; children: React.ReactNode }) {
  const [open, setOpen] = useState(false);
  const [tabSlot, setTabSlot] = useState<HTMLElement | null>(null);
  const pathname = usePathname();
  // Section/sub-tab derived from the path (handles nested routes like /workspace/brief and
  // /client-status/approval) — the `.pop()` segment broke once these became real routes.
  const parts = pathname.split("/").filter(Boolean); // [client, section, sub?]
  const section = parts[1] || "workspace";
  const sub = parts[2];
  const label = LABELS[section] || "Workspace";
  const onStatus = section === "client-status";
  const onWorkspace = section === "workspace";
  const onSummary = section === "performance-summary";
  const statusTab = (onStatus ? sub || "approval" : "approval") as StatusTabKey;
  // Workspace + client-status lift their tab bar into the topbar (portaled into the slot below).
  const showTabSlot = onWorkspace || onStatus;
  const topbarCls =
    "topbar" + (onWorkspace ? " topbar--ws" : "") + (onSummary ? " topbar--bare" : "");

  return (
      <MeProvider>
      <ToastProvider>
        <SessionGuard />
        <div className="app">
          <Sidebar slug={slug} open={open} />
          <div className={"scrim" + (open ? " open" : "")} onClick={() => setOpen(false)} />
          <div className="main">
            <div className={topbarCls}>
              <div className="row">
                <button
                  className="side-toggle"
                  aria-label="Menu"
                  onClick={() => setOpen((o) => !o)}
                >
                  ≡
                </button>
                {showTabSlot ? (
                  <div className="topbar-tabs" ref={setTabSlot} />
                ) : (
                  <div className="crumb">
                    <b data-client-name>{slugToTitle(slug)}</b> <span className="sep">/</span>{" "}
                    {label}
                    {onStatus && (
                      <>
                        {" "}
                        <span className="sep">/</span> {STATUS_LABEL[statusTab]}
                      </>
                    )}
                  </div>
                )}
              </div>
              <div className="topbar-right">
                {onStatus && (
                  <Link href={`/${slug}/${STATUS_BACK[statusTab][0]}`} className="back-btn">
                    {STATUS_BACK[statusTab][1]}
                  </Link>
                )}
              </div>
            </div>
            <TopbarSlotCtx.Provider value={tabSlot}>
              <div className="content">{children}</div>
            </TopbarSlotCtx.Provider>
          </div>
        </div>
      </ToastProvider>
      </MeProvider>
  );
}
