"use client";
import { createContext, useEffect, useState } from "react";
import { usePathname } from "next/navigation";
import Link from "next/link";
import { Sidebar } from "./Sidebar";
import { MeProvider, useMe } from "./MeContext";
import { SessionGuard } from "./SessionGuard";
import { ToastProvider } from "../Toast";
import { slugToTitle } from "@/lib/client";
import { updateUiPrefs } from "@/lib/api";
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

const COLLAPSE_KEY = "hs.sidebar.collapsed";

export function ConsoleShell({ slug, children }: { slug: string; children: React.ReactNode }) {
  return (
    <MeProvider>
      <ToastProvider>
        <SessionGuard />
        <ConsoleBody slug={slug}>{children}</ConsoleBody>
      </ToastProvider>
    </MeProvider>
  );
}

// The console body lives INSIDE MeProvider so it can seed the sidebar collapse state from the
// caller's account preference (`me.ui_prefs`). Split out from ConsoleShell for exactly that reason:
// a hook in ConsoleShell's own body would read the DEFAULT (empty) Me context, since the provider
// sits in ConsoleShell's returned tree, not around it.
function ConsoleBody({ slug, children }: { slug: string; children: React.ReactNode }) {
  const { me } = useMe();
  const [open, setOpen] = useState(false);

  // Desktop icon-rail preference, resolved cheapest-source-first:
  //   1. a localStorage cache — applied on mount so a return visit on THIS browser is instant and
  //      flash-free (no wait on a cold-start /me) and survives even offline;
  //   2. the account value from /me — the source of truth, reconciled in once loaded, so the
  //      preference follows the user across devices.
  // Starts false so SSR and the first client render agree (no hydration mismatch).
  const [collapsed, setCollapsed] = useState(false);
  const serverPref = me?.ui_prefs?.sidebar_collapsed;
  /* eslint-disable react-hooks/set-state-in-effect -- deliberately hydrating this state FROM external
     stores (the house pattern, cf. useListData/list/billing): the localStorage cache on mount (a
     client-only read — unavailable during the SSR render), then the account value from /me once it
     resolves. Neither is derivable during render, so an effect is the correct sync point. */
  useEffect(() => {
    setCollapsed(localStorage.getItem(COLLAPSE_KEY) === "1");
  }, []);
  useEffect(() => {
    if (serverPref === undefined) return; // not loaded yet, or a backend without the field
    setCollapsed(serverPref);
    localStorage.setItem(COLLAPSE_KEY, serverPref ? "1" : "0");
  }, [serverPref]);
  /* eslint-enable react-hooks/set-state-in-effect */

  const toggleCollapsed = () =>
    setCollapsed((c) => {
      const next = !c;
      localStorage.setItem(COLLAPSE_KEY, next ? "1" : "0"); // optimistic local cache
      // Best-effort account sync — swallow failures (offline / older backend without the endpoint);
      // the local cache keeps the setting working this session and it re-syncs next successful call.
      updateUiPrefs({ sidebar_collapsed: next }).catch(() => {});
      return next;
    });

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
    <div className={"app" + (collapsed ? " side-collapsed" : "")}>
      <Sidebar slug={slug} open={open} collapsed={collapsed} onToggleCollapse={toggleCollapsed} />
      <div className={"scrim" + (open ? " open" : "")} onClick={() => setOpen(false)} />
      <div className="main">
        <div className={topbarCls}>
          <div className="row">
            <button className="side-toggle" aria-label="Menu" onClick={() => setOpen((o) => !o)}>
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
  );
}
