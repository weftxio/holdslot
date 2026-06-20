"use client";
import { useMemo, useState } from "react";
import clsx from "clsx";
import { useToast } from "@/components/Toast";
import { highlightBody } from "@/lib/tmpl";
import { nameInitials } from "@/lib/initials";

// ── Outreach Campaigns · funnel view ────────────────────────────────────────
// A single campaign is a funnel: prospects move stage→stage. Each stage can carry
// A/B message variants and a set of prospect company cards. All state is client-side
// mock (no backend); the campaign selector is cosmetic · every existing campaign shows
// the shared sample funnel, a freshly-created one starts empty.

type StageKind = "wip" | "bill" | "exit" | "stop";
type LogEntry = {
  dir: "out" | "in" | "sys";
  ch: "Email" | "LinkedIn" | "Calendar" | "Stripe" | "System";
  when: string;
  title: string;
  body: string;
  meta?: string;
};
type Person = {
  name: string;
  role: string;
  variant?: string;
  sent?: boolean;
  open?: boolean;
  booking?: boolean;
  time?: string;
  amount?: string;
  warn?: string;
  tagline?: string;
  log?: LogEntry[];
};
type Company = { co: string; meta: string; people: Person[] };
type Variant = { id: string; win: boolean; copy: string; open: number; reply: number };
type VariantSet = { label: string; sub: string; items: Variant[] };
type Stage = {
  id: string;
  kind: StageKind;
  title: string;
  step: string;
  vol: number;
  conv: string;
  drop?: string;
  obj: string;
  variants: VariantSet | null;
  cards: Company[];
};

// Allowed stage moves: forward one, back one, plus Drop/DNC. Drop re-opens to outreach.
const MOVES: Record<string, string[]> = {
  contacted: ["followup", "drop"],
  followup: ["contacted", "replied", "drop"],
  replied: ["followup", "meeting", "drop"],
  meeting: ["replied", "billable", "noshow", "drop"],
  noshow: ["meeting", "replied", "drop"],
  billable: ["meeting", "drop"],
  drop: ["contacted"],
};

// Sample funnel · illustrative data for the mock. Tokens use the {{name}} syntax shared
// with the brief/email templates so highlightBody() renders them.
const SAMPLE_FUNNEL: Stage[] = [
  {
    id: "contacted",
    kind: "wip",
    title: "Initial outreach",
    step: "S3",
    vol: 40,
    conv: "40 of 40 contacted",
    obj: "Get the email opened and earn a first reply.",
    variants: {
      label: "Outreach message",
      sub: "3 variants · 40 sent",
      items: [
        { id: "A", win: true, copy: "Hi {{first_name}}, quick note on {{company}}'s {{pain}} · one-line value prop, soft ask for a short call.", open: 48, reply: 15 },
        { id: "B", win: false, copy: "Hi {{first_name}}, pattern-interrupt opener + proof point with a concrete number. Direct ask for {{time_window}}.", open: 41, reply: 10 },
        { id: "C", win: false, copy: "Hi {{first_name}}, question-led opener about {{industry}}. Mutual-connection line + low-friction ask.", open: 39, reply: 9 },
      ],
    },
    cards: [
      {
        co: "Northwind Logistics",
        meta: "Freight · 220 ppl",
        people: [
          {
            name: "Dana R.",
            role: "VP Ops",
            variant: "A",
            sent: true,
            open: true,
            log: [
              { dir: "out", ch: "Email", when: "Jun 9, 9:02 AM", title: "Outreach · Variant A", body: "Hi Dana, quick note on Northwind's carrier-onboarding lag · we cut it ~40% for similar 3PLs. Worth a short call?", meta: "Opened 2×" },
              { dir: "out", ch: "LinkedIn", when: "Jun 9, 9:05 AM", title: "Connection request", body: "Sent connection request with a one-line intro.", meta: "Accepted" },
              { dir: "in", ch: "Email", when: "Jun 11, 1:24 PM", title: "Reply from Dana", body: "Interesting timing · we're scoping this for Q3. Can you send a one-pager?", meta: "Positive" },
            ],
          },
          { name: "Marcus T.", role: "Logistics Lead", variant: "B", sent: false },
        ],
      },
      { co: "Atlas Robotics", meta: "Hardware · 80 ppl", people: [{ name: "Sam K.", role: "COO", variant: "B", sent: true, open: false }] },
      {
        co: "Cedar & Co.",
        meta: "Retail · 1.2k ppl",
        people: [
          { name: "Priya M.", role: "Head of CX", variant: "A", sent: true, open: true },
          { name: "Devin R.", role: "Ops Manager", variant: "A", sent: false },
          { name: "Tara V.", role: "CX Analyst", variant: "C", sent: false },
        ],
      },
      { co: "Lumen Health", meta: "Healthtech · 140", people: [{ name: "Eli T.", role: "CTO", variant: "C", sent: true, open: false }] },
    ],
  },
  {
    id: "followup",
    kind: "wip",
    title: "Follow-up",
    step: "S4",
    vol: 28,
    conv: "28 still awaiting reply",
    drop: "-30% no-reply",
    obj: "Re-engage non-responders before the sequence ends.",
    variants: {
      label: "Follow-up message",
      sub: "2 variants · 28 sent",
      items: [
        { id: "A", win: false, copy: "Bumping this up, {{first_name}} · short bump + restate value in one line. Yes/no ask.", open: 33, reply: 7 },
        { id: "B", win: true, copy: "{{first_name}}, sharing a 20-sec case study relevant to {{company}}. Worth a look?", open: 38, reply: 11 },
      ],
    },
    cards: [
      {
        co: "Briar Financial",
        meta: "Fintech · 300 ppl",
        people: [
          { name: "Owen P.", role: "Director", variant: "B", sent: true, open: true },
          { name: "Hana S.", role: "VP Finance", variant: "A", sent: false },
        ],
      },
      { co: "Vela Studios", meta: "Agency · 45 ppl", people: [{ name: "Mara L.", role: "Founder", variant: "A", sent: true, open: false }] },
      { co: "Peak Supply", meta: "Distribution · 90", people: [{ name: "Jon V.", role: "Owner", variant: "B", sent: true, open: true }] },
    ],
  },
  {
    id: "replied",
    kind: "wip",
    title: "Positive reply",
    step: "S4→S5",
    vol: 5,
    conv: "5 positive replies",
    obj: "Convert a positive reply into a booked meeting.",
    variants: {
      label: "Booking message",
      sub: "2 variants · 5 sent",
      items: [
        { id: "A", win: true, copy: "Great to hear, {{first_name}}! Here's my link · grab any slot that works. {{calendar_link}}", open: 100, reply: 60 },
        { id: "B", win: false, copy: "Glad this resonates. Does {{day_option_1}} or {{day_option_2}} suit you for 20 min?", open: 100, reply: 40 },
      ],
    },
    cards: [
      { co: "Harbor Point", meta: "Real estate · 60", people: [{ name: "Lena F.", role: "GM", variant: "A", sent: true, booking: true }] },
      {
        co: "Orbit Media",
        meta: "Media · 110 ppl",
        people: [
          { name: "Theo N.", role: "VP Growth", variant: "A", sent: true, booking: true },
          { name: "Cass W.", role: "Marketing Dir.", variant: "B", sent: false },
        ],
      },
    ],
  },
  {
    id: "meeting",
    kind: "wip",
    title: "Meeting schedule",
    step: "S5",
    vol: 2,
    conv: "2 meetings booked",
    obj: "Prospect shows up and passes the duration / fit check.",
    variants: {
      label: "Reminder message",
      sub: "1 variant · 2 sent",
      items: [{ id: "A", win: false, copy: "See you {{meeting_time}}, {{first_name}}. Reply here if anything shifts · link again: {{link}}", open: 100, reply: 50 }],
    },
    cards: [{ co: "Harbor Point", meta: "Real estate · 60", people: [{ name: "Lena F.", role: "GM", variant: "A", sent: true, time: "Thu 2:00 PM" }] }],
  },
  {
    id: "noshow",
    kind: "exit",
    title: "No show",
    step: "S5",
    vol: 2,
    conv: "2 missed · re-book or park",
    obj: "Booked but did not attend · re-book or park for a future touch.",
    variants: {
      label: "Re-book message",
      sub: "2 variants · 4 sent",
      items: [
        { id: "A", win: true, copy: "Sorry we missed each other, {{first_name}}! Things come up · here's my link to grab a new time: {{calendar_link}}", open: 62, reply: 28 },
        { id: "B", win: false, copy: "No worries on the missed call, {{first_name}}. Want me to send a couple of fresh slots for {{time_window}}?", open: 55, reply: 19 },
      ],
    },
    cards: [
      { co: "Vela Studios", meta: "Agency · 45 ppl", people: [{ name: "Mara L.", role: "Founder", variant: "A", sent: true, open: true }] },
      {
        co: "Pine Ridge Co.",
        meta: "Construction · 70",
        people: [
          { name: "Gus W.", role: "Owner", variant: "A", sent: false },
          { name: "Nadia E.", role: "Project Lead", variant: "B", sent: false },
        ],
      },
    ],
  },
  {
    id: "billable",
    kind: "bill",
    title: "Qualified billable",
    step: "S6",
    vol: 1,
    conv: "1 confirmed · Stripe",
    obj: "Held meeting confirmed · pushed to Stripe as a line item.",
    variants: null,
    cards: [{ co: "Orbit Media", meta: "Media · 110 ppl", people: [{ name: "Theo N.", role: "VP Growth", sent: true, amount: "$1,500" }] }],
  },
  {
    id: "drop",
    kind: "stop",
    title: "Drop / DNC",
    step: "S4",
    vol: 6,
    conv: "6 negative / opted out",
    obj: "Graceful exit on negative or do-not-contact replies.",
    variants: {
      label: "Drop message",
      sub: "2 variants · 6 sent",
      items: [
        { id: "A", win: true, copy: "Understood, {{first_name}} · I'll close this out. If timing changes, the door's open. All the best.", open: 90, reply: 20 },
        { id: "B", win: false, copy: "No problem at all. Removing you from this thread · wishing the {{company}} team well.", open: 85, reply: 12 },
      ],
    },
    cards: [
      { co: "Iron Gate Mfg.", meta: "Manufacturing · 500", people: [{ name: "Carl H.", role: "Plant Mgr", variant: "A", sent: true, warn: "Not interested" }] },
      { co: "Solace Foods", meta: "CPG · 230 ppl", people: [{ name: "Ria D.", role: "Buyer", variant: "B", sent: true, warn: "Unsubscribed" }] },
    ],
  },
];

// A new campaign that hasn't been sent · same stages, no prospects, no variants yet.
const EMPTY_FUNNEL: Stage[] = SAMPLE_FUNNEL.map((s) => ({ ...s, vol: 0, conv: "No prospects yet", drop: undefined, variants: null, cards: [] }));

// Stage id → title, stable across every funnel (used for move toasts and the move dropdown).
const STAGE_TITLE: Record<string, string> = Object.fromEntries(SAMPLE_FUNNEL.map((s) => [s.id, s.title]));

// When a new campaign locks its batch, its prospects enter the Initial outreach stage.
// Fresh outreach variants (no sends yet) and a representative set of sample prospects.
const SEED_VARIANTS: VariantSet = {
  label: "Outreach message",
  sub: "3 variants · 0 sent",
  items: [
    { id: "A", win: false, copy: "Hi {{first_name}}, quick note on {{company}}'s {{pain}} · one-line value prop, soft ask for a short call.", open: 0, reply: 0 },
    { id: "B", win: false, copy: "Hi {{first_name}}, pattern-interrupt opener + a concrete proof point. Direct ask for {{time_window}}.", open: 0, reply: 0 },
    { id: "C", win: false, copy: "Hi {{first_name}}, question-led opener about {{industry}}. Mutual-connection line + low-friction ask.", open: 0, reply: 0 },
  ],
};
const SEED_COMPANIES: Company[] = [
  { co: "Quill & Vane", meta: "SaaS · 120 ppl", people: [{ name: "Alex P.", role: "Head of Sales", variant: "A", sent: false }, { name: "Robin K.", role: "RevOps", variant: "A", sent: false }] },
  { co: "Maple Grid", meta: "Energy · 300 ppl", people: [{ name: "Sam D.", role: "VP Ops", variant: "B", sent: false }] },
  { co: "Brightline", meta: "Logistics · 75 ppl", people: [{ name: "Jordan T.", role: "COO", variant: "A", sent: false }, { name: "Casey M.", role: "Ops Lead", variant: "C", sent: false }] },
];
// Build a fresh funnel for a newly-locked campaign: prospects land in "contacted", unsent.
function seedFunnel(count: number): Stage[] {
  return EMPTY_FUNNEL.map((s) =>
    s.id !== "contacted"
      ? { ...s }
      : {
          ...s,
          vol: count,
          conv: `${count} prospects ready`,
          variants: { ...SEED_VARIANTS, items: SEED_VARIANTS.items.map((v) => ({ ...v })) },
          cards: SEED_COMPANIES.map((c) => ({ ...c, people: c.people.map((p) => ({ ...p })) })),
        }
  );
}

const LOGO = ["#5e7c9e", "#3e8e6e", "#9bb7d6", "#c08a3e", "#c25b53", "#4a6b7a"];
const logoFor = (s: string) => LOGO[[...s].reduce((a, c) => a + c.charCodeAt(0), 0) % LOGO.length];

// Build a default conversation thread for a sent prospect without an explicit log.
function buildLog(p: Person, kind: StageKind): LogEntry[] {
  if (p.log) return p.log;
  if (!p.sent) return [];
  const fn = p.name.split(" ")[0];
  const v = p.variant ? `Variant ${p.variant}` : "Message";
  if (kind === "stop")
    return [
      { dir: "out", ch: "Email", when: "Jun 8, 10:14 AM", title: `Outreach · ${v}`, body: `Initial outreach sent to ${fn}.`, meta: p.open ? "Opened" : "Unopened" },
      { dir: "in", ch: "Email", when: "Jun 10, 4:02 PM", title: `Reply from ${fn}`, body: p.warn === "Unsubscribed" ? "Please remove me from this list." : "Not a fit for us right now.", meta: "Negative" },
      { dir: "out", ch: "Email", when: "Jun 10, 4:20 PM", title: `Drop · ${v}`, body: "Acknowledged and closed the thread. Door left open for later.", meta: "Sent" },
    ];
  if (kind === "bill")
    return [
      { dir: "out", ch: "Email", when: "Jun 7, 8:40 AM", title: "Outreach · Variant A", body: `Initial outreach sent to ${fn}.`, meta: "Opened 3×" },
      { dir: "in", ch: "Email", when: "Jun 9, 11:10 AM", title: `Reply from ${fn}`, body: "Yes, let's find time.", meta: "Positive" },
      { dir: "out", ch: "Calendar", when: "Jun 9, 11:30 AM", title: "Meeting booked", body: "20-min intro call scheduled and held.", meta: "Held" },
      { dir: "out", ch: "Stripe", when: "Jun 12, 9:00 AM", title: "Qualified billable", body: `Pushed to Stripe as a ${p.amount} line item.`, meta: "Invoiced" },
    ];
  if (kind === "exit") {
    const rows: LogEntry[] = [
      { dir: "out", ch: "Calendar", when: "Jun 9, 10:00 AM", title: "Meeting booked", body: `Intro call scheduled with ${fn}.`, meta: "Booked" },
      { dir: "sys", ch: "System", when: "Jun 11, 2:05 PM", title: "No-show", body: `${fn} did not attend the scheduled call.`, meta: "Missed" },
    ];
    rows.push({ dir: "out", ch: "Email", when: "Jun 11, 2:30 PM", title: `Re-book · ${v}`, body: "Sent a friendly re-book message with a fresh calendar link.", meta: p.open ? "Opened" : "Sent" });
    return rows;
  }
  const rows: LogEntry[] = [
    { dir: "out", ch: "Email", when: "Jun 8, 9:30 AM", title: `Outreach · ${v}`, body: `Initial outreach sent to ${fn}.`, meta: p.open ? "Opened" : "Unopened" },
    { dir: "out", ch: "LinkedIn", when: "Jun 8, 9:33 AM", title: "Connection request", body: "Sent alongside the email.", meta: p.open ? "Accepted" : "Pending" },
  ];
  if (p.booking) rows.push({ dir: "out", ch: "Email", when: "Jun 10, 2:15 PM", title: "Booking · Variant A", body: "Sent calendar link to lock a slot.", meta: "Booking sent" });
  if (p.time) rows.push({ dir: "out", ch: "Calendar", when: "Jun 10, 3:00 PM", title: "Meeting booked", body: `Provisionally scheduled for ${p.time}.`, meta: "Pending" });
  return rows;
}

// ── Component ────────────────────────────────────────────────────────────────
type CampaignRef = { name: string; batch: string; locked: boolean };

export function CampaignTab({
  campaigns,
  batchOptions,
  onNewCampaign,
  onSetBatch,
  onConfirm,
  onRename,
}: {
  campaigns: CampaignRef[];
  batchOptions: { name: string; count: number }[];
  onNewCampaign: () => string | null;
  onSetBatch: (name: string, batch: string) => void;
  onConfirm: (name: string) => void;
  onRename: (oldName: string, newName: string) => void;
}) {
  const toast = useToast();
  // One funnel per campaign, keyed by name. Mount-time campaigns start on the sample funnel;
  // a campaign created this session has no entry until its batch is locked (then seedFunnel
  // populates it), so until then it falls back to the empty funnel. Updates are immutable, so
  // campaigns that share the initial SAMPLE_FUNNEL reference diverge cleanly on first edit.
  const [funnels, setFunnels] = useState<Record<string, Stage[]>>(() =>
    Object.fromEntries(campaigns.map((c) => [c.name, SAMPLE_FUNNEL]))
  );
  const [selected, setSelected] = useState(campaigns[0]?.name ?? "Campaign 1");
  const [stageId, setStageId] = useState("contacted");
  const [openLogs, setOpenLogs] = useState<Set<string>>(new Set());
  const [editKey, setEditKey] = useState<string | null>(null); // "<stageId>:<variantId>"

  const view = funnels[selected] ?? EMPTY_FUNNEL;
  const stage = view.find((s) => s.id === stageId) ?? view[0];
  const maxVol = Math.max(...view.map((s) => s.vol), 1);

  // Apply an update to the selected campaign's funnel.
  const updateView = (updater: (stages: Stage[]) => Stage[]) =>
    setFunnels((prev) => ({ ...prev, [selected]: updater(prev[selected] ?? EMPTY_FUNNEL) }));

  const cp = campaigns.find((c) => c.name === selected) ?? campaigns[0];
  const volOf = (id: string) => view.find((s) => s.id === id)?.vol ?? 0;
  const kpis = useMemo(
    () => [
      { lbl: "Prospects", val: volOf("contacted") },
      { lbl: "Replies", val: volOf("replied") },
      { lbl: "Meetings", val: volOf("meeting") + volOf("billable") },
      { lbl: "Billable", val: volOf("billable"), accent: true },
    ],
    [view] // eslint-disable-line react-hooks/exhaustive-deps
  );

  // ── mutations (operate on the selected campaign's funnel) ──
  const patchStage = (id: string, fn: (s: Stage) => Stage) =>
    updateView((prev) => prev.map((s) => (s.id === id ? fn(s) : s)));
  const patchVariants = (id: string, fn: (items: Variant[]) => Variant[]) =>
    patchStage(id, (s) => (s.variants ? { ...s, variants: { ...s.variants, items: fn(s.variants.items) } } : s));

  const sendPerson = (sid: string, ci: number, pi: number) => {
    patchStage(sid, (s) => ({
      ...s,
      cards: s.cards.map((c, cx) =>
        cx !== ci ? c : { ...c, people: c.people.map((p, px) => (px !== pi ? p : { ...p, sent: true, open: false })) }
      ),
    }));
    toast("Message sent");
  };

  const setPersonVariant = (sid: string, ci: number, pi: number, vid: string) =>
    patchStage(sid, (s) => ({
      ...s,
      cards: s.cards.map((c, cx) =>
        cx !== ci ? c : { ...c, people: c.people.map((p, px) => (px !== pi ? p : { ...p, variant: vid })) }
      ),
    }));

  const movePerson = (srcId: string, ci: number, pi: number, targetId: string) => {
    if (!MOVES[srcId]?.includes(targetId)) return;
    updateView((prev) => {
      const next = prev.map((s) => ({ ...s, cards: s.cards.map((c) => ({ ...c, people: [...c.people] })) }));
      const src = next.find((s) => s.id === srcId)!;
      const tgt = next.find((s) => s.id === targetId)!;
      const srcCard = src.cards[ci];
      if (!srcCard) return prev;
      const [person] = srcCard.people.splice(pi, 1);
      if (!person) return prev;
      if (srcCard.people.length === 0) src.cards.splice(src.cards.indexOf(srcCard), 1);
      const minSrc = src.cards.reduce((n, c) => n + c.people.length, 0);
      src.vol = Math.max(src.vol - 1, minSrc);
      // Entering a stage that sends a message resets the prospect to a fresh, unsent state.
      const fresh: Person = { name: person.name, role: person.role, variant: person.variant };
      const carry = tgt.variants ? fresh : person;
      let dest = tgt.cards.find((c) => c.co === srcCard.co);
      if (!dest) {
        dest = { co: srcCard.co, meta: srcCard.meta, people: [] };
        tgt.cards.push(dest);
      }
      dest.people.push(carry);
      tgt.vol = tgt.vol + 1;
      return next;
    });
    // Card/people indices shift after a move; openLogs is index-keyed, so clear it
    // to avoid an expanded thread re-attaching to a different prospect.
    setOpenLogs(new Set());
    toast(`Moved to ${STAGE_TITLE[targetId]}`);
  };

  const editVariant = (sid: string, vid: string) => {
    const key = `${sid}:${vid}`;
    if (editKey === key) {
      setEditKey(null);
      toast(`Variant ${vid} saved`);
    } else setEditKey(key);
  };
  const setVariantCopy = (sid: string, vid: string, copy: string) =>
    patchVariants(sid, (items) => items.map((v) => (v.id === vid ? { ...v, copy } : v)));
  const addVariant = (sid: string) => {
    patchVariants(sid, (items) => {
      let code = 65;
      while (items.some((v) => v.id === String.fromCharCode(code))) code++;
      const id = String.fromCharCode(code);
      return [...items, { id, win: false, copy: "New variant · write your message. Use {{first_name}} and {{company}} tokens.", open: 0, reply: 0 }];
    });
    toast("Variant added");
  };
  const deleteVariant = (sid: string, vid: string) => {
    patchVariants(sid, (items) => {
      if (items.length <= 1) {
        toast("Keep at least one variant", "warn");
        return items;
      }
      const wasWin = items.find((v) => v.id === vid)?.win;
      const left = items
        .filter((v) => v.id !== vid)
        .map((v, k) => ({ ...v, id: String.fromCharCode(65 + k) }));
      if (wasWin && left.length) left[0].win = true;
      toast(`Variant ${vid} removed`, "warn");
      return left;
    });
  };

  const toggleLog = (pid: string) =>
    setOpenLogs((s) => {
      const next = new Set(s);
      next.has(pid) ? next.delete(pid) : next.add(pid);
      return next;
    });

  const selectStage = (id: string) => {
    setStageId(id);
    setOpenLogs(new Set());
  };

  // Create a draft campaign and jump to it so the operator can pick a batch and confirm.
  const handleNewCampaign = () => {
    const name = onNewCampaign();
    if (name) {
      setSelected(name);
      selectStage("contacted");
    }
  };

  // Lock the batch and seed its prospects into the Initial outreach stage.
  const handleConfirm = () => {
    if (!cp) return;
    onConfirm(cp.name);
    const count = batchOptions.find((b) => b.name === cp.batch)?.count ?? 0;
    setFunnels((prev) => ({ ...prev, [cp.name]: seedFunnel(count) }));
    selectStage("contacted");
  };

  // Rename the selected campaign, rekeying its name-keyed funnel.
  const commitRename = (raw: string) => {
    const next = raw.trim();
    if (!next || next === selected) return;
    if (campaigns.some((c) => c.name === next)) {
      toast("That campaign name is already in use", "warn");
      return;
    }
    const old = selected;
    onRename(old, next);
    setFunnels((prev) => {
      if (!(old in prev)) return prev;
      const { [old]: f, ...rest } = prev;
      return { ...rest, [next]: f };
    });
    setSelected(next);
    toast(`Renamed to ${next}`);
  };

  return (
    <>
      {/* Top bar: campaign selector + KPIs + locked batch */}
      <div className="cmp-top">
        <label className="cmp-top-field">
          <select
            className="select select-sm"
            aria-label="Campaign"
            value={selected}
            onChange={(e) => {
              setSelected(e.target.value);
              selectStage("contacted");
            }}
          >
            {campaigns.map((c) => (
              <option key={c.name}>{c.name}</option>
            ))}
          </select>
        </label>
        <input
          key={selected}
          className="input cmp-name-input"
          defaultValue={selected}
          aria-label="Edit campaign name"
          title="Edit campaign name"
          onBlur={(e) => commitRename(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") e.currentTarget.blur();
          }}
        />
        <div className="cmp-top-actions">
        <div className="cmp-kpis">
          {kpis.map((k) => (
            <div key={k.lbl} className={clsx("cmp-kpi", k.accent && "accent")}>
              <div className="cmp-kpi-lbl">{k.lbl}</div>
              <div className="cmp-kpi-val">{k.val}</div>
            </div>
          ))}
        </div>
        {cp && !cp.locked ? (
          <div className="cmp-batch draft">
            <span className="cmp-batch-lbl">Sendout batch</span>
            <select
              className="select select-sm"
              value={cp.batch}
              aria-label="Select sendout batch"
              onChange={(e) => onSetBatch(cp.name, e.target.value)}
            >
              {batchOptions.map((b) => (
                <option key={b.name}>{b.name}</option>
              ))}
            </select>
            <button type="button" className="btn btn-accent btn-sm" onClick={handleConfirm}>
              Confirm &amp; lock
            </button>
          </div>
        ) : (
          <div className="cmp-batch" title="Sendout batch · locked when the campaign was confirmed">
            <svg
              className="cmp-batch-lock"
              width="12"
              height="12"
              viewBox="0 0 14 14"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.5"
            >
              <rect x="3" y="6.2" width="8" height="5.5" rx="1.2" />
              <path d="M4.6 6.2V4.6a2.4 2.4 0 0 1 4.8 0v1.6" />
            </svg>
            <span className="cmp-batch-lbl">Sendout batch</span>
            <span className="cmp-batch-name">{cp?.batch ?? "·"}</span>
          </div>
        )}
        <button type="button" className="btn btn-ghost btn-sm" onClick={handleNewCampaign}>
          ＋ New campaign
        </button>
        </div>
      </div>

      <div className="cmp-shell">
        {/* Funnel rail */}
        <aside className="cmp-rail">
          <div className="cmp-eyebrow">Funnel · click a stage</div>
          <div className="cmp-funnel">
            {view.map((s) => (
              <button
                key={s.id}
                type="button"
                className={clsx("cmp-stage", s.id === stage.id && "active")}
                data-kind={s.kind}
                onClick={() => selectStage(s.id)}
              >
                <div className="cmp-stage-top">
                  <span className="cmp-sw" />
                  <span className="cmp-nm">{s.title}</span>
                  <span className="cmp-ct">{s.vol}</span>
                </div>
                <div className="cmp-bar">
                  <i style={{ width: `${Math.max(6, Math.round((s.vol / maxVol) * 100))}%` }} />
                </div>
                <div className="cmp-conv">
                  <b>{s.conv}</b>
                  {s.drop && <span className="cmp-drop">{s.drop}</span>}
                </div>
              </button>
            ))}
          </div>
        </aside>

        {/* Detail */}
        <main className="cmp-detail">
          {/* Variant testing · only for stages that send an outbound message */}
          {stage.variants && (
            <>
              <div className="cmp-sec">
                A/B variant testing
                <span className="cmp-pill">{stage.variants.sub}</span>
              </div>
              <VariantPanel
                stage={stage}
                editKey={editKey}
                onEdit={editVariant}
                onCopy={setVariantCopy}
                onAdd={() => addVariant(stage.id)}
                onDelete={(vid) => deleteVariant(stage.id, vid)}
              />
            </>
          )}

          {/* Prospects in stage */}
          <div className="cmp-sec">
            Prospects in this stage <span className="cmp-pill">{stage.cards.length} companies</span>
          </div>
          {stage.cards.length ? (
            <div className="cmp-cards">
              {stage.cards.map((c, ci) => (
                <CompanyCard
                  key={c.co + ci}
                  company={c}
                  ci={ci}
                  stage={stage}
                  openLogs={openLogs}
                  onToggleLog={toggleLog}
                  onSend={sendPerson}
                  onVariant={setPersonVariant}
                  onMove={movePerson}
                />
              ))}
            </div>
          ) : (
            <div className="cmp-empty">No prospects in this stage yet</div>
          )}
        </main>
      </div>
    </>
  );
}

// ── Variant panel ─────────────────────────────────────────────────────────────
function VariantPanel({
  stage,
  editKey,
  onEdit,
  onCopy,
  onAdd,
  onDelete,
}: {
  stage: Stage;
  editKey: string | null;
  onEdit: (sid: string, vid: string) => void;
  onCopy: (sid: string, vid: string, copy: string) => void;
  onAdd: () => void;
  onDelete: (vid: string) => void;
}) {
  return (
    <div className="cmp-vars">
      {stage.variants!.items.map((v) => {
        const editing = editKey === `${stage.id}:${v.id}`;
        return (
          <div key={v.id} className={clsx("cmp-v", v.win && "win")}>
            <div className="cmp-vbadge">{v.id}</div>
            <div className="cmp-vmain">
              <div className="cmp-vtop">
                <span className="cmp-vname">Variant {v.id}</span>
                {v.win && (
                  <span className="cmp-lead" title="Leading by reply rate">
                    <span className="cmp-lead-d" />
                    Leading
                  </span>
                )}
              </div>
              {editing ? (
                <textarea
                  className="textarea cmp-vedit"
                  value={v.copy}
                  onChange={(e) => onCopy(stage.id, v.id, e.target.value)}
                />
              ) : (
                <div className="cmp-vcopy">{highlightBody(v.copy)}</div>
              )}
            </div>
            <div className="cmp-vmetrics">
              <div className="cmp-m">
                <div className="cmp-m-num">{v.open}%</div>
                <div className="cmp-m-cap">Open</div>
              </div>
              <div className="cmp-m">
                <div className={clsx("cmp-m-num", v.win && "good")}>{v.reply}%</div>
                <div className="cmp-m-cap">Reply</div>
              </div>
            </div>
            <div className="cmp-vact">
              <button
                type="button"
                className={clsx("cmp-vbtn edit", editing && "active")}
                title={editing ? `Save variant ${v.id}` : `Edit variant ${v.id}`}
                aria-label={editing ? `Save variant ${v.id}` : `Edit variant ${v.id}`}
                onClick={() => onEdit(stage.id, v.id)}
              >
                <svg
                  width="14"
                  height="14"
                  viewBox="0 0 16 16"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="1.5"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                >
                  <path d="M11.5 2.5l2 2L6 12l-2.5.5L4 10z" />
                  <path d="M10 4l2 2" />
                </svg>
              </button>
              <button
                type="button"
                className="cmp-vbtn del"
                title={`Delete variant ${v.id}`}
                aria-label={`Delete variant ${v.id}`}
                onClick={() => onDelete(v.id)}
              >
                <svg
                  width="14"
                  height="14"
                  viewBox="0 0 16 16"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="1.5"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                >
                  <path d="M3 4.5h10M6.5 4.5V3h3v1.5M5 4.5l.5 8h5l.5-8" />
                </svg>
              </button>
            </div>
          </div>
        );
      })}
      <div className="cmp-vfoot">
        <button type="button" className="cmp-add" onClick={onAdd}>
          ＋ Add variant
        </button>
      </div>
    </div>
  );
}

// ── Company card + people ──────────────────────────────────────────────────────
function personStatus(p: Person) {
  if (p.amount) return <span className="cmp-chip amount">{p.amount} · Stripe</span>;
  if (p.warn) return <span className="cmp-chip warn">{p.warn}</span>;
  if (p.time) return <span className="cmp-chip time">{p.time}</span>;
  if (p.booking) return <span className="cmp-rate">Booking sent</span>;
  if (p.sent) return <span className="cmp-rate">{p.open ? "Opened" : "Sent · unopened"}</span>;
  return <span className="cmp-rate pending">Not sent</span>;
}

function CompanyCard({
  company,
  ci,
  stage,
  openLogs,
  onToggleLog,
  onSend,
  onVariant,
  onMove,
}: {
  company: Company;
  ci: number;
  stage: Stage;
  openLogs: Set<string>;
  onToggleLog: (pid: string) => void;
  onSend: (sid: string, ci: number, pi: number) => void;
  onVariant: (sid: string, ci: number, pi: number, vid: string) => void;
  onMove: (sid: string, ci: number, pi: number, targetId: string) => void;
}) {
  const targets = MOVES[stage.id] ?? [];
  return (
    <div className="cmp-card" data-kind={stage.kind}>
      <div className="cmp-crow">
        <div className="cmp-logo" style={{ background: logoFor(company.co) }}>
          {nameInitials(company.co)}
        </div>
        <div className="cmp-co">
          <div className="cmp-cname">{company.co}</div>
          <div className="cmp-cmeta">{company.meta}</div>
        </div>
        <span className="cmp-pcount">
          {company.people.length} {company.people.length === 1 ? "contact" : "contacts"}
        </span>
      </div>
      <div className="cmp-people">
        {company.people.map((p, pi) => {
          const pid = `${stage.id}-${ci}-${pi}`;
          const log = buildLog(p, stage.kind);
          const open = openLogs.has(pid);
          const canSend = !p.sent && !!stage.variants;
          return (
            <div key={pi} className={clsx("cmp-person", open && "log-open")}>
              <div className="cmp-prow">
                <div className="cmp-av">{nameInitials(p.name)}</div>
                <div className="cmp-pid">
                  <div className="cmp-pname">{p.name}</div>
                  <div className="cmp-prole">{p.role}</div>
                </div>
                {stage.variants && (
                  <select
                    className={clsx("cmp-vsel", p.sent && "locked")}
                    value={p.variant ?? stage.variants.items[0]?.id}
                    disabled={p.sent}
                    aria-label={`Variant for ${p.name}`}
                    onChange={(e) => onVariant(stage.id, ci, pi, e.target.value)}
                  >
                    {stage.variants.items.map((v) => (
                      <option key={v.id} value={v.id}>
                        Var {v.id}
                      </option>
                    ))}
                  </select>
                )}
              </div>
              <div className="cmp-pfoot">
                {personStatus(p)}
                <span className="cmp-spacer" />
                {log.length > 0 && (
                  <button
                    type="button"
                    className="cmp-logtoggle"
                    aria-expanded={open}
                    onClick={() => onToggleLog(pid)}
                  >
                    Log
                    <span className="cmp-logcount">{log.length}</span>
                    <span className="cmp-chev" aria-hidden>
                      ⌄
                    </span>
                  </button>
                )}
                {canSend && (
                  <button type="button" className="cmp-send" onClick={() => onSend(stage.id, ci, pi)}>
                    Send
                  </button>
                )}
              </div>
              {log.length > 0 && (
                <div className="cmp-log-wrap">
                  <div className="cmp-log-inner">
                    {log.map((e, li) => (
                      <div key={li} className={clsx("cmp-logrow", e.dir)}>
                        <div className="cmp-lograil">
                          <span className="cmp-logdot" />
                        </div>
                        <div className="cmp-logbody">
                          <div className="cmp-logtop">
                            <span className={clsx("cmp-logch", e.ch.toLowerCase())}>{e.ch}</span>
                            <span className="cmp-logtitle">{e.title}</span>
                            <span className="cmp-logwhen">{e.when}</span>
                          </div>
                          <div className="cmp-logmsg">{e.body}</div>
                          {e.meta && <div className="cmp-logmeta">{e.meta}</div>}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
              {targets.length > 0 && (
                <div className="cmp-move">
                  <span className="cmp-move-lbl">Stage</span>
                  <select
                    className="cmp-movesel"
                    value=""
                    aria-label={`Move ${p.name} to another stage`}
                    onChange={(e) => {
                      if (e.target.value) onMove(stage.id, ci, pi, e.target.value);
                    }}
                  >
                    <option value="" disabled>
                      Move stage…
                    </option>
                    {targets.map((id) => (
                      <option key={id} value={id}>
                        {STAGE_TITLE[id]}
                      </option>
                    ))}
                  </select>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
