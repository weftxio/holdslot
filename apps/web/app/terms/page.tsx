import type { Metadata } from "next";
import { LegalPage } from "@/components/LegalPage";

export const metadata: Metadata = { title: "HoldSlot · Terms of Service" };

export default function Terms() {
  return (
    <LegalPage title="Terms of Service" updated="June 2026">
      <p>
        These terms govern your use of HoldSlot, a done-for-you service that books qualified sales
        meetings. By using HoldSlot you agree to them.
      </p>

      <h2>1 · The service</h2>
      <p>
        We source and verify prospects against your brief, run email outreach, handle replies, and
        schedule meetings onto your calendar. You approve every prospect list before any outreach
        begins.
      </p>

      <h2>2 · Pricing &amp; billing</h2>
      <ul>
        <li>
          <strong>Base fee</strong> — a monthly fee covers sourcing, copywriting, sending, and inbox
          management.
        </li>
        <li>
          <strong>Per qualified meeting</strong> — you are charged only when a qualified meeting
          actually takes place. No-shows and short calls are never billable.
        </li>
        <li>No setup fee, no long-term retainer; you can cancel anytime.</li>
      </ul>

      <h2>3 · Your responsibilities</h2>
      <p>
        You confirm you have the right to market the products described in your brief, and that your
        offer and claims are accurate. You are responsible for attending the meetings booked for you.
      </p>

      <h2>4 · Acceptable use</h2>
      <p>
        Campaigns must comply with applicable anti-spam and data-protection laws. We honour
        unsubscribe and do-not-contact requests, and we may pause a campaign that risks
        non-compliance.
      </p>

      <h2>5 · Qualified-meeting definition</h2>
      <p>
        A meeting is &quot;qualified&quot; when the prospect matches the approved criteria, attends,
        and the call meets the agreed minimum duration. Disputes are reviewed against the recorded
        meeting metadata and audit trail.
      </p>

      <h2>6 · Liability</h2>
      <p>
        HoldSlot is provided on a commercially reasonable basis. We are not liable for indirect or
        consequential losses arising from campaign outcomes.
      </p>

      <h2>7 · Contact</h2>
      <p>
        Questions about these terms? Email <a href="mailto:hello@holdslot.com">hello@holdslot.com</a>
        .
      </p>
    </LegalPage>
  );
}
