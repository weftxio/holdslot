"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import "./home.css";

const clamp = (v: number, a: number, b: number) => Math.max(a, Math.min(b, v));
const validEmail = (e: string) => /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(e);

export default function Home() {
  const [menuOpen, setMenuOpen] = useState(false);
  const [email, setEmail] = useState("");
  const [emailErr, setEmailErr] = useState(false);
  const [msg, setMsg] = useState("");
  const [sent, setSent] = useState(false);
  const [sending, setSending] = useState(false);

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
    const trustVisual = document.querySelector<HTMLElement>(".trust-visual");

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
      if (trustVisual && !reduced) {
        const r = trustVisual.getBoundingClientRect();
        const center = r.top + r.height / 2 - vh / 2;
        trustVisual.style.transform = "translateY(" + clamp(-center * 0.05, -26, 26) + "px)";
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
              without the cost of building an in-house sales team.
            </p>
            <div className="hero-ctas">
              <a href="#start" className="btn btn-primary">
                Get started <span className="arrow">→</span>
              </a>
              <a href="#how" className="btn btn-ghost">
                See how it works
              </a>
            </div>
            <p className="hero-note">
              You approve every prospect before we reach out.{" "}
              <b>You only pay for meetings that actually happen.</b>
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
          <div className="stat-grid reveal">
            <div className="stat">
              <div className="num">
                <span className="ph-inline ph">
                  <span className="ph-tag">stat</span>
                </span>
              </div>
              <div className="label">Qualified meetings booked for clients</div>
            </div>
            <div className="stat">
              <div className="num">
                <span className="ph-inline ph">
                  <span className="ph-tag">stat</span>
                </span>
                %
              </div>
              <div className="label">Average meeting show-up rate</div>
            </div>
            <div className="stat">
              <div className="num">
                <span className="ph-inline ph">
                  <span className="ph-tag">stat</span>
                </span>
              </div>
              <div className="label">Cost vs. one in-house SDR hire</div>
            </div>
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
                You stay in control at every gate. We handle the rest. Scroll to follow a campaign
                from start to booked.
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
                  Tell us who your ideal customer is, what you sell, and who to avoid. We turn it
                  into a structured campaign in minutes.
                </p>
              </div>
              <div className="flow-step dim" data-step="1">
                <div className="n">02</div>
                <h3>Approve your list</h3>
                <p>
                  We build and verify a prospect list against your rules. Nothing gets contacted
                  until you approve it in one click.
                </p>
              </div>
              <div className="flow-step dim" data-step="2">
                <div className="n">03</div>
                <h3>We run the outreach</h3>
                <p>
                  Messages go out from warmed inboxes. Replies are read, sorted, and answered.
                  Positive ones surface to you instantly.
                </p>
              </div>
              <div className="flow-step dim" data-step="3">
                <div className="n">04</div>
                <h3>You take the meeting</h3>
                <p>
                  Interested buyers land on your calendar. You only get billed when a real,
                  qualified meeting takes place.
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
            <h2>Built for teams who can&apos;t afford a miss.</h2>
            <ul className="trust-list">
              <li className="anim">
                <span className="check">✓</span>
                <div>
                  <strong>You approve every prospect.</strong>
                  <span>
                    Your brand never touches a list you haven&apos;t signed off on. Full
                    transparency, full control.
                  </span>
                </div>
              </li>
              <li className="anim">
                <span className="check">✓</span>
                <div>
                  <strong>You only pay for meetings that happen.</strong>
                  <span>
                    No-shows and short calls aren&apos;t billable. One number matters: qualified
                    meetings booked.
                  </span>
                </div>
              </li>
              <li className="anim">
                <span className="check">✓</span>
                <div>
                  <strong>Replaces a whole SDR function.</strong>
                  <span>
                    Sourcing, writing, sending, follow-up, and scheduling, without hiring, training,
                    or managing a team.
                  </span>
                </div>
              </li>
            </ul>
          </div>
          <div className="trust-visual ph reveal">
            <span className="ph-tag">
              Placeholder · secondary product shot · list / approval view
            </span>
          </div>
        </div>
      </section>

      <section className="pricing" id="pricing">
        <div className="wrap">
          <div className="sec-head anim">
            <span className="eyebrow">Pricing</span>
            <p>
              A small base keeps the engine running. The rest you only pay when a real meeting lands
              on your calendar. We win when you win.
            </p>
          </div>
          <div className="formula">
            <div className="fterm base anim">
              <div className="ft-cap">Base</div>
              <div className="ft-amt">
                HKD 6,000<small> /mo</small>
              </div>
              <div className="ft-sub">
                Sourcing, copywriting, sending &amp; inbox management, always on.
              </div>
            </div>
            <div className="fop anim">+</div>
            <div className="fterm anim">
              <div className="ft-cap">Per meeting</div>
              <div className="ft-amt">HKD 4,000</div>
              <div className="ft-sub">
                Charged only when a qualified meeting actually takes place.
              </div>
            </div>
            <div className="fop anim">×</div>
            <div className="fterm anim">
              <div className="ft-cap">Meetings booked</div>
              <div className="ft-amt">you decide</div>
              <div className="ft-sub">
                No-shows and short calls are never billed. You stay in control.
              </div>
            </div>
          </div>
        </div>
      </section>

      <section className="final" id="start">
        <div className="wrap">
          <div className="final-card reveal">
            <div className={"form-state" + (sent ? " hide" : "")}>
              <span className="pill">Pay per qualified meeting</span>
              <h2>See 25 of your buyers, free.</h2>
              <p className="lead-copy">
                Drop your work email and we&apos;ll send a sample list of 25 qualified prospects
                matched to your ideal customer. No call required, no commitment.
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
                  {sending ? "Sending…" : "Get my free list"} <span className="arrow">→</span>
                </button>
              </div>
              <div className={"form-msg" + (msg ? " error" : "")}>{msg}</div>
              <p className="price-line">
                Then: <b>pay only per qualified meeting</b>. No setup fee, no retainer, cancel
                anytime.
              </p>
            </div>
            <div className={"success-state" + (sent ? " show" : "")}>
              <div className="tick">✓</div>
              <h2>Your list is on the way.</h2>
              <p className="lead-copy">
                We&apos;ll send 25 matched prospects to {email.trim() || "your inbox"} shortly. Keep
                an eye out.
              </p>
              <p className="final-sub" style={{ marginTop: 24 }}>
                Want to move faster?{" "}
                <a href="#" onClick={(e) => e.preventDefault()}>
                  Book a 15-min walkthrough →
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
