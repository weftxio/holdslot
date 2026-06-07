import React from "react";

// Highlight {{tokens}} in a single line of template text as <span className="mph">.
// Shared by the workspace variant editor and the client-status email templates so the
// token syntax and highlight markup live in one place.
export function highlightTokens(text: string): React.ReactNode[] {
  return text.split(/(\{\{[^}]+\}\})/g).map((p, i) =>
    /^\{\{.*\}\}$/.test(p) ? (
      <span key={i} className="mph">
        {p}
      </span>
    ) : (
      p
    )
  );
}

// Same as highlightTokens but preserves single newlines as <br/> (multi-line bodies).
export function highlightBody(text: string): React.ReactNode[] {
  return text.split("\n").map((line, li) => (
    <span key={li}>
      {li > 0 && <br />}
      {highlightTokens(line)}
    </span>
  ));
}
