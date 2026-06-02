"use client";
import { useEffect, useState } from "react";
import clsx from "clsx";

export type LinkState = "valid" | "expired";

/** Reads the demo `?state=expired` param once on mount; returns toggleable state. */
export function useLinkState() {
  const [state, setState] = useState<LinkState>("valid");
  useEffect(() => {
    if (new URLSearchParams(window.location.search).get("state") === "expired") {
      setState("expired");
    }
  }, []);
  return [state, setState] as const;
}

export function StateToggle({
  state,
  onChange,
}: {
  state: LinkState;
  onChange: (s: LinkState) => void;
}) {
  return (
    <div className="state-toggle" role="group" aria-label="Demo state">
      <span className="st-label">Link state</span>
      <button className={clsx(state === "valid" && "on")} onClick={() => onChange("valid")}>
        Valid
      </button>
      <button className={clsx(state === "expired" && "on")} onClick={() => onChange("expired")}>
        Expired
      </button>
    </div>
  );
}
