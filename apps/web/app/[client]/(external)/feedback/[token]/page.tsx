"use client";
import { useState } from "react";
import clsx from "clsx";
import { Sample } from "@/components/Sample";
import { ExternalShell } from "@/components/external/ExternalShell";
import "./feedback.css";

const LABELS: Record<number, string> = {
  1: "Not worthwhile",
  2: "Below expectations",
  3: "Okay",
  4: "Worthwhile",
  5: "Excellent, would meet again",
};
const CHIPS = ["Relevant to me", "Good timing", "Well prepared", "Not a fit", "Too early"];

export default function Feedback() {
  const [rating, setRating] = useState(0);
  const [hover, setHover] = useState(0);
  const [chips, setChips] = useState<Record<string, boolean>>({});
  const [comment, setComment] = useState("");
  const [err, setErr] = useState("");
  const [done, setDone] = useState(false);

  const shown = hover || rating;

  function submit() {
    if (!rating) {
      setErr("Please pick a rating first.");
      return;
    }
    setDone(true);
  }

  const success = (
    <div className="success-inner">
      <div className="tick">✓</div>
      <h1>Thank you.</h1>
      <p>
        Your feedback&apos;s been recorded. It helps HoldSlot make every introduction more relevant,
        and it confirms this meeting for the host.
      </p>
      <p className="muted" style={{ fontSize: 13, marginTop: 16 }}>
        You can close this page now.
      </p>
    </div>
  );

  return (
    <ExternalShell
      narrow
      secure="🔒 Secure link · 30 seconds"
      footBy="Feedback by HoldSlot"
      footNote="Anonymous to other prospects."
      expiredTitle="This feedback link has expired"
      expiredLines={[
        "Feedback links stay open for a short window after the meeting. This one has closed.",
        "That's completely fine. No action needed on your end.",
      ]}
      success={success}
      done={done}
    >
      <div className="ext-head">
        <span className="eyebrow">Quick feedback</span>
        <h1>How was your meeting?</h1>
        <p>
          Thanks for meeting with <b>Northwind</b> <Sample>sample</Sample>. A few seconds of
          feedback helps us keep these intros relevant. It goes only to HoldSlot &amp; the host.
        </p>
      </div>
      <div className="ext-pad">
        <div className="rate-block">
          <div className="rate-q">Overall, how worthwhile was the meeting?</div>
          <div className="stars" onMouseLeave={() => setHover(0)}>
            {[1, 2, 3, 4, 5].map((v) => (
              <button
                key={v}
                className={clsx(
                  "star",
                  v <= shown && "on",
                  v <= rating && !hover && "deep",
                  hover && v <= hover && "on"
                )}
                aria-label={`${v} star${v > 1 ? "s" : ""}`}
                onMouseEnter={() => setHover(v)}
                onClick={() => {
                  setRating(v);
                  setErr("");
                }}
              >
                ★
              </button>
            ))}
          </div>
          <div className="rate-label">{shown ? LABELS[shown] : ""}</div>
          <div className="field-err center">{err}</div>
        </div>

        <div className="divider">And was it relevant?</div>

        <div className="qual-chips">
          {CHIPS.map((c) => (
            <button
              key={c}
              className={clsx("chip", chips[c] && "on")}
              onClick={() => setChips((s) => ({ ...s, [c]: !s[c] }))}
            >
              {c}
            </button>
          ))}
        </div>

        <div className="field" style={{ margin: "24px 0 18px" }}>
          <label htmlFor="comment">
            Anything to add? <span className="opt">· optional</span>
          </label>
          <textarea
            className="textarea"
            id="comment"
            placeholder="Placeholder: what was useful, or what would have made it better."
            value={comment}
            onChange={(e) => setComment(e.target.value)}
          />
        </div>

        <button className="btn btn-primary" style={{ width: "100%" }} onClick={submit}>
          Submit feedback <span className="arrow">→</span>
        </button>
        <p className="muted" style={{ fontSize: 12, textAlign: "center", marginTop: 14 }}>
          Your rating won&apos;t be shared with anyone you&apos;d meet again.
        </p>
      </div>
    </ExternalShell>
  );
}
