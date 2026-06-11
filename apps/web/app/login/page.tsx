"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { DEFAULT_CLIENT_SLUG } from "@/lib/client";
import { login as apiLogin, forgot as apiForgot, getMe, setTokens } from "@/lib/api";
import { useCountUp } from "@/lib/useCountUp";
import "./login.css";

const validEmail = (e: string) => /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(e);
type View = "signin" | "forgot" | "sent";

// Proof stats — mock figures that count up on load (mirrors the homepage strip).
const PROOF: { from: number; to: number; fmt: (v: number) => string; label: string }[] = [
  {
    from: 0,
    to: 640,
    fmt: (v) => v.toLocaleString("en-US") + "+",
    label: "Meetings booked this quarter",
  },
  { from: 0, to: 92, fmt: (v) => v + "%", label: "Average show-up rate" },
];

export default function Login() {
  const router = useRouter();
  const [view, setView] = useState<View>("signin");
  // Count the proof stats up on mount.
  const proof = useCountUp(PROOF);

  const [email, setEmail] = useState("");
  const [pw, setPw] = useState("");
  const [showPw, setShowPw] = useState(false);
  const [emailErr, setEmailErr] = useState("");
  const [pwErr, setPwErr] = useState("");
  const [banner, setBanner] = useState(false);
  const [signing, setSigning] = useState(false);

  const [resetEmail, setResetEmail] = useState("");
  const [resetErr, setResetErr] = useState("");
  const [resetCopy, setResetCopy] = useState(
    "If an account exists for that address, a reset link is on its way. The link stays valid for 30 minutes."
  );

  async function signin(e: React.FormEvent) {
    e.preventDefault();
    let ok = true;
    if (!validEmail(email.trim())) {
      setEmailErr("Enter a valid work email.");
      ok = false;
    }
    if (pw.length < 6) {
      setPwErr("Password must be at least 6 characters.");
      ok = false;
    }
    if (!ok) return;
    setSigning(true);
    setBanner(false);
    try {
      const res = await apiLogin(email.trim(), pw);
      setTokens(res.access_token, res.refresh_token);
      // Land on the caller's first tenant (HoldSlot today); fall back to the default slug.
      const me = await getMe().catch(() => null);
      const slug = me?.clients[0]?.slug ?? DEFAULT_CLIENT_SLUG;
      router.push(`/${slug}/overview`);
    } catch {
      setPwErr("Invalid email or password.");
      setBanner(true);
      setSigning(false);
    }
  }

  function sendReset() {
    const v = resetEmail.trim();
    if (!validEmail(v)) {
      setResetErr("Enter a valid work email.");
      return;
    }
    void apiForgot(v); // best-effort; endpoint always accepts, never reveals existence
    setResetCopy(
      `If an account exists for ${v}, a reset link is on its way. The link stays valid for 30 minutes.`
    );
    setView("sent");
  }

  return (
    <div className="auth">
      <div className="auth-brand">
        <Link
          href="/"
          className="logo"
          title="Back to homepage"
          aria-label="HoldSlot · back to homepage"
        >
          <span className="dot" />
          HoldSlot
        </Link>
        <div className="auth-lead">
          <span className="eyebrow">Operator console</span>
          <h2>
            Qualified meetings, <em>booked for you.</em>
          </h2>
          <p>
            Sign in to run your campaign. Approve lists, review replies, and watch real meetings
            land on the calendar.
          </p>
          <div className="auth-proof" style={{ marginTop: 30 }}>
            {PROOF.map((s, i) => (
              <div className="p" key={s.label}>
                <div className="n">{s.fmt(proof[i])}</div>
                <div className="l">{s.label}</div>
              </div>
            ))}
          </div>
        </div>
        <div className="auth-foot-links">
          <Link href="/privacy">Privacy</Link>
          <Link href="/terms">Terms</Link>
        </div>
      </div>

      <div className="auth-form-side">
        <form className="auth-form" onSubmit={signin} noValidate>
          <Link
            href="/"
            className="logo mob-logo"
            title="Back to homepage"
            aria-label="HoldSlot · back to homepage"
          >
            <span className="dot" />
            HoldSlot
          </Link>

          {view === "signin" && (
            <div>
              <h1>Sign in</h1>
              <p className="lead">Welcome back. Sign in to open your console.</p>

              <div className={"form-banner" + (banner ? " show" : "")}>
                <span>✕</span>
                <span>Those credentials don&apos;t match our records.</span>
              </div>

              <div className="field">
                <label htmlFor="email">Work email</label>
                <input
                  className={"input" + (emailErr ? " err" : "")}
                  type="email"
                  id="email"
                  placeholder="you@company.com"
                  autoComplete="email"
                  value={email}
                  onChange={(e) => {
                    setEmail(e.target.value);
                    setEmailErr("");
                    setBanner(false);
                  }}
                />
                <div className="field-err">{emailErr}</div>
              </div>

              <div className="field">
                <div className="field-row">
                  <label htmlFor="pw">Password</label>
                  <a
                    href="#"
                    onClick={(e) => {
                      e.preventDefault();
                      setResetEmail(email);
                      setResetErr("");
                      setView("forgot");
                    }}
                  >
                    Forgot?
                  </a>
                </div>
                <div className="pw-wrap">
                  <input
                    className={"input" + (pwErr ? " err" : "")}
                    type={showPw ? "text" : "password"}
                    id="pw"
                    placeholder="••••••••"
                    autoComplete="current-password"
                    style={{ paddingRight: 60 }}
                    value={pw}
                    onChange={(e) => {
                      setPw(e.target.value);
                      setPwErr("");
                      setBanner(false);
                    }}
                  />
                  <button type="button" className="pw-toggle" onClick={() => setShowPw((s) => !s)}>
                    {showPw ? "Hide" : "Show"}
                  </button>
                </div>
                <div className="field-hint">Use at least 6 characters.</div>
                <div className="field-err">{pwErr}</div>
              </div>

              <button type="submit" className="btn btn-primary" disabled={signing}>
                {signing ? "Signing in…" : "Sign in"}
              </button>

              <p className="alt">
                New to HoldSlot? <Link href="/#start">Get started</Link>
              </p>
            </div>
          )}

          {view === "forgot" && (
            <div>
              <h1>Reset your password</h1>
              <p className="lead">
                Enter your work email and we&apos;ll send you a link to set a new password.
              </p>
              <div className="field">
                <label htmlFor="resetEmail">Work email</label>
                <input
                  className={"input" + (resetErr ? " err" : "")}
                  type="email"
                  id="resetEmail"
                  placeholder="you@company.com"
                  autoComplete="email"
                  value={resetEmail}
                  onChange={(e) => {
                    setResetEmail(e.target.value);
                    setResetErr("");
                  }}
                  onKeyDown={(e) => e.key === "Enter" && (e.preventDefault(), sendReset())}
                />
                <div className="field-err">{resetErr}</div>
              </div>
              <button
                type="button"
                className="btn btn-primary"
                style={{ width: "100%" }}
                onClick={sendReset}
              >
                Send reset link
              </button>
              <p className="alt">
                <a href="#" onClick={(e) => (e.preventDefault(), setView("signin"))}>
                  Back to sign in
                </a>
              </p>
            </div>
          )}

          {view === "sent" && (
            <div style={{ textAlign: "center" }}>
              <div className="reset-tick">✓</div>
              <h1>Check your inbox</h1>
              <p className="lead" style={{ marginBottom: 24 }}>
                {resetCopy}
              </p>
              <button
                type="button"
                className="btn btn-ghost"
                style={{ width: "100%" }}
                onClick={() => setView("signin")}
              >
                Back to sign in
              </button>
              <p className="demo-hint">
                Didn&apos;t get it? Check spam, or{" "}
                <a
                  href="#"
                  style={{ color: "var(--cerulean-deep)", fontWeight: 600 }}
                  onClick={(e) => (e.preventDefault(), setView("forgot"))}
                >
                  send again
                </a>
                .
              </p>
            </div>
          )}
        </form>
      </div>
    </div>
  );
}
