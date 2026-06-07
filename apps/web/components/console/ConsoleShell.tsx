"use client";
import { useState } from "react";
import { usePathname } from "next/navigation";
import Link from "next/link";
import { Sidebar } from "./Sidebar";
import { ToastProvider } from "../Toast";
import { slugToTitle } from "@/lib/client";
import { StatusTabCtx, STATUS_LABEL, STATUS_BACK, type StatusTabKey } from "./StatusTab";

const LABELS: Record<string, string> = {
  overview: "Overview",
  workspace: "Workspace",
  "client-status": "Client Action",
};

export function ConsoleShell({ slug, children }: { slug: string; children: React.ReactNode }) {
  const [open, setOpen] = useState(false);
  const [statusTab, setStatusTab] = useState<StatusTabKey>("approval");
  const pathname = usePathname();
  const seg = pathname.split("/").pop() || "overview";
  const label = LABELS[seg] || "Overview";
  const onStatus = seg === "client-status";

  return (
    <StatusTabCtx.Provider value={{ tab: statusTab, setTab: setStatusTab }}>
      <ToastProvider>
        <div className="app">
          <Sidebar slug={slug} open={open} />
          <div className={"scrim" + (open ? " open" : "")} onClick={() => setOpen(false)} />
          <div className="main">
            <div className="topbar">
              <div className="row">
                <button
                  className="side-toggle"
                  aria-label="Menu"
                  onClick={() => setOpen((o) => !o)}
                >
                  ≡
                </button>
                <div className="crumb">
                  <b data-client-name>{slugToTitle(slug)}</b> <span className="sep">/</span> {label}
                  {onStatus && (
                    <>
                      {" "}
                      <span className="sep">/</span> {STATUS_LABEL[statusTab]}
                    </>
                  )}
                </div>
              </div>
              <div className="topbar-right">
                {onStatus && (
                  <Link href={`/${slug}/${STATUS_BACK[statusTab][0]}`} className="back-btn">
                    {STATUS_BACK[statusTab][1]}
                  </Link>
                )}
              </div>
            </div>
            <div className="content">{children}</div>
          </div>
        </div>
      </ToastProvider>
    </StatusTabCtx.Provider>
  );
}
