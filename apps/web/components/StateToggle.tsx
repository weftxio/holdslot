"use client";
import { useState } from "react";
import { useSearchParams } from "next/navigation";
import clsx from "clsx";

export type LinkState = "valid" | "expired";

/** Reads the demo `?state=expired` param; returns toggleable state. */
export function useLinkState() {
  // useSearchParams is SSR-consistent on these dynamic external routes, so seed the initial state
  // from it directly — no mount effect, no hydration mismatch.
  const expired = useSearchParams().get("state") === "expired";
  const [state, setState] = useState<LinkState>(expired ? "expired" : "valid");
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
