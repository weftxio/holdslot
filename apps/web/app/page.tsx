"use client";
import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useCountUp } from "@/lib/useCountUp";
import "./home.css";

const clamp = (v: number, a: number, b: number) => Math.max(a, Math.min(b, v));
const validEmail = (e: string) => /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(e);

// Result-proof strip — mock figures that count up each time the strip scrolls
// into view (the "refresh" animation). `from`→`to` is the animated range.
const STATS: { from: number; to: number; fmt: (v: number) => string; label: string }[] = [
  {
    from: 0,
    to: 2480,
    fmt: (v) => v.toLocaleString("en-US") + "+",
    label: "Qualified meetings booked for clients",
  },
  { from: 0, to: 92, fmt: (v) => v + "%", label: "Average meeting show-up rate" },
  { from: 0, to: 30, fmt: (v) => v + "%", label: "Cost vs. one in-house SDR hire" },
];

export default function Home() {
  const [menuOpen, setMenuOpen] = useState(false);
  const [email, setEmail] = useState("");
  const [emailErr, setEmailErr] = useState(false);
  const [msg, setMsg] = useState("");
  const [sent, setSent] = useState(false);
  const [sending, setSending] = useState(false);
  // Count the result-proof strip up each time it scrolls into view.
  const statsRef = useRef<HTMLDivElement>(null);
  const counts = useCountUp(STATS, statsRef);

  // reveal + scroll-driven flow + parallax (ported from home.html)
  useEffect(() => {
    const io = new IntersectionObserver(
      (es) =>
        es.forEach(
          (e) => e.isIntersecting && (e.target.classList.add("in"), io.unobserve(e.target))
        ),
      { threshold: 0.12 }
    );
    document.querySelectorAll(".reveal,.anim").forEach((el) => io.observe(el));

    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const howFlow = document.getElementById("how");
    const flowFill = document.getElementById("flowFill");
    const flowSteps = howFlow
      ? Array.from(howFlow.querySelectorAll<HTMLElement>(".flow-step"))
      : [];

    function update() {
      const vh = window.innerHeight;
      document.querySelectorAll(".reveal:not(.in),.anim:not(.in)").forEach((el) => {
        if (el.getBoundingClientRect().top < vh * 0.92) el.classList.add("in");
      });
      if (howFlow && flowSteps.length) {
        if (window.innerWidth <= 880 || reduced) {
          flowSteps.forEach((s) => s.classList.remove("dim", "active"));
          if (flowFill) flowFill.style.width = "100%";
        } else {
          const rect = howFlow.getBoundingClientRect();
          const total = howFlow.offsetHeight - vh;
          const p = total > 0 ? clamp(-rect.top / total, 0, 1) : 0;
          if (flowFill) flowFill.style.width = p * 100 + "%";
          const active = Math.min(flowSteps.length - 1, Math.floor(p * flowSteps.length + 0.0001));
          flowSteps.forEach((s, i) => {
            s.classList.toggle("active", i === active);
            s.classList.toggle("dim", i > active);
          });
        }
      }
    }
    let ticking = false;
    const onScroll = () => {
      if (!ticking) {
        requestAnimationFrame(() => {
          update();
          ticking = false;
        });
        ticking = true;
      }
    };
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", update);
    update();
    return () => {
      io.disconnect();
      window.removeEventListener("scroll", onScroll);
      window.removeEventListener("resize", update);
    };
  }, []);

  function submit() {
    const v = email.trim();
    if (!validEmail(v)) {
      setEmailErr(true);
      setMsg("Please enter a valid work email.");
      return;
    }
    setEmailErr(false);
    setMsg("");
    setSending(true);
    setTimeout(() => setSent(true), 650);
  }

  return (
    <div className="home">
      <header>
        <div className="wrap">
          <nav>
            <a href="#top" className="logo">
              <span className="dot" />
              HoldSlot
            </a>
            <div className="nav-links">
              <a href="#how">How it works</a>
              <a href="#trust">Why HoldSlot</a>
              <a href="#pricing">Pricing</a>
            </div>
            <div className="nav-cta">
              <Link href="/login" className="btn btn-ghost" style={{ padding: "11px 18px" }}>
                Log in
              </Link>
              <a href="#start" className="btn btn-primary" style={{ padding: "11px 18px" }}>
                Get started
              </a>
              <button
                className="menu-btn"
                aria-label="Open menu"
                onClick={() => setMenuOpen((o) => !o)}
              >
                {menuOpen ? "✕" : "≡"}
              </button>
            </div>
          </nav>
        </div>
        <div
          className={"mobile-menu" + (menuOpen ? " open" : "")}
          onClick={() => setMenuOpen(false)}
        >
          <a href="#how">How it works</a>
          <a href="#trust">Why HoldSlot</a>
          <a href="#pricing">Pricing</a>
          <Link href="/login" className="btn btn-ghost">
            Log in
          </Link>
          <a href="#start" className="btn btn-primary">
            Get started
          </a>
        </div>
      </header>

      <span id="top" />

      <section className="hero">
        <div className="wrap hero-grid">
          <div className="reveal">
            <span className="eyebrow">Outbound, done for you</span>
            <h1>
              Qualified sales meetings, <em>booked for you.</em>
            </h1>
            <p className="sub">
              We find your buyers, start the conversations, and put real meetings on your calendar,
              without the cost of building an <span className="nowrap">in-house</span> sales team.
            </p>
            <div className="hero-ctas">
              <a href="#start" className="btn btn-primary">
                Get started
              </a>
              <a href="#how" className="btn btn-ghost">
                See how it works
              </a>
            </div>
            <p className="hero-note">
              You approve every prospect before we reach out.
              <br />
              <b>You pay for domain setup, prospect sourcing, and meetings that actually happen.</b>
            </p>
          </div>
          <div className="hero-visual ph reveal">
            <span className="ph-tag">
              Placeholder · product shot · &quot;meetings booked&quot; dashboard / calendar
            </span>
          </div>
        </div>
      </section>

      <section className="stats">
        <div className="wrap">
          <div className="stat-grid reveal" ref={statsRef}>
            {STATS.map((s, i) => (
              <div className="stat" key={s.label}>
                <div className="num">{s.fmt(counts[i])}</div>
                <div className="label">{s.label}</div>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="how-flow" id="how">
        <div className="how-sticky">
          <div className="wrap">
            <div className="flow-head">
              <span className="eyebrow">How it works</span>
              <h2>From brief to booked meeting.</h2>
              <p>
                You stay in control at every gate. We handle the rest.
                <br />
                Scroll to follow a campaign from start to booked.
              </p>
            </div>
            <div className="flow-track">
              <div className="flow-line">
                <div className="fill" id="flowFill" />
              </div>
              <div className="flow-step active" data-step="0">
                <div className="n">01</div>
                <h3>Share your brief</h3>
                <p>
                  Tell us who you sell to, what you offer, and who to avoid. We turn it into a
                  campaign in minutes.
                </p>
              </div>
              <div className="flow-step dim" data-step="1">
                <div className="n">02</div>
                <h3>Approve your target</h3>
                <p>
                  We build a prospect list that matches your rules. Nobody gets contacted until you
                  approve it.
                </p>
              </div>
              <div className="flow-step dim" data-step="2">
                <div className="n">03</div>
                <h3>We run the outreach</h3>
                <p>
                  Emails go out from warmed inboxes. We read and sort every reply, and send the good
                  ones straight to you.
                </p>
              </div>
              <div className="flow-step dim" data-step="3">
                <div className="n">04</div>
                <h3>You take the meeting</h3>
                <p>
                  Buyers book straight onto your calendar. You pay the meeting fee only when a real,
                  qualified meeting happens.
                </p>
              </div>
            </div>
          </div>
        </div>
      </section>

      <section className="trust" id="trust">
        <div className="wrap trust-grid">
          <div className="reveal">
            <span className="eyebrow">Why HoldSlot</span>
            <h2>Scale your business with no wasted spend.</h2>
            <ul className="trust-list">
              <li className="anim">
                <span className="check">✓</span>
                <div>
                  <strong>You approve every prospect.</strong>
                  <span>
                    Your brand never touches a list you haven&apos;t signed off on.
                    <br />
                    Full transparency, full control.
                  </span>
                </div>
              </li>
              <li className="anim">
                <span className="check">✓</span>
                <div>
                  <strong>Meetings are billed only when they happen.</strong>
                  <span>
                    No-shows and short calls aren&apos;t billable.
                    <br />
                    One number matters: qualified meetings booked.
                  </span>
                </div>
              </li>
              <li className="anim">
                <span className="check">✓</span>
                <div>
                  <strong>Multiply Sales Pipeline with AI</strong>
                  <span>
                    Sourcing, writing, sending, follow-up, and scheduling, without hiring, training,
                    or managing a team.
                  </span>
                </div>
              </li>
            </ul>
          </div>
          <div className="trust-visual flowchart reveal">
            <div className="fc-node fc-input">
              <span className="fc-kicker">01 · Approve</span>
              <span className="fc-title">Approve the prospect</span>
              <span className="fc-meta">Review selected list · approve in one click</span>
            </div>

            <div className="fc-wire" aria-hidden="true">
              <span className="fc-dot" />
            </div>

            <div className="fc-node fc-engine">
              <span className="fc-kicker">02 · Meet</span>
              <span className="fc-title">Join the confirmed meeting</span>
              <div className="fc-chips">
                <span>Buyer intent</span>
                <span>Warmed relationship</span>
                <span>Aligned datetime</span>
              </div>
            </div>

            <div className="fc-wire" aria-hidden="true">
              <span className="fc-dot" style={{ animationDelay: "1s" }} />
            </div>

            <div className="fc-node fc-output">
              <span className="fc-kicker">03 · Grow</span>
              <span className="fc-title">
                Accelerate your sales
                <br />
                Amplify your growth
              </span>
            </div>
          </div>
        </div>
      </section>

      <section className="pricing" id="pricing">
        <div className="wrap">
          <div className="sec-head anim">
            <span className="eyebrow">Pricing</span>
            <h2>Minimal retainer. Pay per meeting.</h2>
            <p>Full alignment on your growth.</p>
          </div>

          <div className="tier-grid">
            <div className="tier anim">
              <div className="tier-head">
                <div className="tier-name">Free</div>
                <div className="tier-tag">Test the fit</div>
              </div>
              <div className="tier-price">
                <span className="tp-amt">$0</span>
                <span className="tp-sub">no card required</span>
              </div>
              <a href="#start" className="btn btn-ghost tier-cta">
                Get 10 free prospects
              </a>
              <ul className="tier-feats">
                <li>1 brief + 1 ICP draft</li>
                <li>10 prospects, one-time</li>
                <li className="no">No outbound sending</li>
              </ul>
            </div>

            <div className="tier feat anim">
              <div className="tier-badge">Most popular</div>
              <div className="tier-head">
                <div className="tier-name">Launch</div>
                <div className="tier-tag">Your first pipeline</div>
              </div>
              <div className="tier-price">
                <div className="tp-row">
                  <span className="tp-amt">
                    $800<small> /mo</small>
                  </span>
                  <span className="tp-meet">
                    + $500<small> /meeting</small>
                  </span>
                </div>
                <span className="tp-act">+ $400 one-time activation</span>
              </div>
              <a href="#start" className="btn btn-accent tier-cta">
                Start Launch
              </a>
              <ul className="tier-feats">
                <li>1 ICP</li>
                <li>Up to 150 prospects / mo</li>
                <li>Done-for-you outbound</li>
              </ul>
            </div>

            <div className="tier anim">
              <div className="tier-head">
                <div className="tier-name">Growth</div>
                <div className="tier-tag">Scale the engine</div>
              </div>
              <div className="tier-price">
                <div className="tp-row">
                  <span className="tp-amt">
                    $1,600<small> /mo</small>
                  </span>
                  <span className="tp-meet">
                    + $500<small> /meeting</small>
                  </span>
                </div>
                <span className="tp-act">+ $400 one-time activation</span>
              </div>
              <a href="#start" className="btn btn-primary tier-cta">
                Start Growth
              </a>
              <ul className="tier-feats">
                <li>Up to 3 ICPs</li>
                <li>Up to 400 prospects / mo</li>
                <li>Done-for-you outbound</li>
              </ul>
            </div>
          </div>

          <div className="billing-strip anim">
            <div className="bs-head">What each fee pays for</div>
            <div className="bs-items">
              <div className="bs-item">
                <div className="bs-fee">
                  Activation <span>$400 &middot; one-time</span>
                </div>
                <p>
                  Your own domains and mailboxes, warmed before sending, so your outreach lands
                  instead of going to spam.
                </p>
              </div>
              <div className="bs-item">
                <div className="bs-fee">
                  Monthly <span>$800 Launch / $1,600 Growth</span>
                </div>
                <p>
                  The engine behind your pipeline: enrichment, sending infrastructure, AI, and
                  operator-run outreach. Paid whether or not meetings book.
                </p>
              </div>
              <div className="bs-item">
                <div className="bs-fee">
                  Per meeting <span>$500 &middot; qualified only</span>
                </div>
                <p>
                  A pre-approved buyer who showed up to a 10-minute-plus meeting and passed the
                  48-hour dispute window.
                </p>
              </div>
            </div>
            <div className="bs-note">
              Overage &middot; $3 per prospect beyond your monthly cap. No-shows and short calls are
              never billed.
            </div>
          </div>
        </div>
      </section>

      <section className="final" id="start">
        <div className="wrap">
          <div className="final-card reveal">
            <div className={"form-state" + (sent ? " hide" : "")}>
              <span className="pill">Pay per qualified meeting</span>
              <h2>See 10 of your potential buyers.</h2>
              <p className="lead-copy">
                Verify your market fit. Enter your work email for a complimentary target account
                brief and 10 high-value prospects. No calls, no financial commitment.
              </p>
              <div className="lead-form">
                <input
                  type="email"
                  className={emailErr ? "err" : undefined}
                  placeholder="you@company.com"
                  aria-label="Work email"
                  autoComplete="email"
                  value={email}
                  onChange={(e) => {
                    setEmail(e.target.value);
                    if (emailErr) {
                      setEmailErr(false);
                      setMsg("");
                    }
                  }}
                  onKeyDown={(e) => e.key === "Enter" && submit()}
                />
                <button className="btn" onClick={submit}>
                  {sending ? "Sending…" : "Get my free list"}
                </button>
              </div>
              <div className={"form-msg" + (msg ? " error" : "")}>{msg}</div>
              <p className="price-line">
                <b>Pay for setup, sourcing, and qualified meetings</b>, cancel anytime.
              </p>
            </div>
            <div className={"success-state" + (sent ? " show" : "")}>
              <div className="tick">✓</div>
              <h2>Your list is on the way.</h2>
              <p className="lead-copy">
                We&apos;ll send 10 matched prospects to {email.trim() || "your inbox"} shortly. Keep
                an eye out.
              </p>
              <p className="final-sub" style={{ marginTop: 24 }}>
                Want to move faster?{" "}
                <a href="#" onClick={(e) => e.preventDefault()}>
                  Book a 15-min walkthrough
                </a>
              </p>
            </div>
          </div>
        </div>
      </section>

      <footer>
        <div className="wrap">
          <div className="foot-row">
            <a href="#top" className="logo">
              <span className="dot" />
              HoldSlot
            </a>
            <div className="foot-links">
              <a href="#how">How it works</a>
              <a href="#trust">Why HoldSlot</a>
              <a href="#pricing">Pricing</a>
              <Link href="/privacy">Privacy</Link>
              <Link href="/terms">Terms</Link>
            </div>
          </div>
          <p className="foot-copy">© 2026 HoldSlot. Qualified sales meetings, booked for you.</p>
        </div>
      </footer>
    </div>
  );
}
