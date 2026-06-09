import type { Metadata } from "next";
import { LegalPage } from "@/components/LegalPage";

export const metadata: Metadata = { title: "HoldSlot · Privacy Policy" };

export default function Privacy() {
  return (
    <LegalPage title="Privacy Policy" updated="June 2026">
      <p>
        HoldSlot (&quot;we&quot;, &quot;us&quot;) runs done-for-you outbound campaigns on behalf of
        our clients. This policy explains what data we collect, why, and how we handle it.
      </p>

      <h2>1 · What we collect</h2>
      <ul>
        <li>
          <strong>Client account data</strong> — operator name, work email, and the campaign brief
          you provide.
        </li>
        <li>
          <strong>Prospect data</strong> — business contact details (name, role, company, work
          email) sourced and enriched to match your ideal-customer criteria.
        </li>
        <li>
          <strong>Engagement data</strong> — message delivery, opens, replies, bookings, and
          meeting outcomes used to report results and bill qualified meetings.
        </li>
      </ul>

      <h2>2 · How we use it</h2>
      <p>
        We use the data to source and verify prospect lists, run outreach from warmed inboxes,
        classify replies, schedule meetings, and produce meeting summaries. Billing covers
        activation, the monthly fee, and qualified meetings that take place.
      </p>

      <h2>3 · Recording &amp; consent</h2>
      <p>
        Meetings booked through HoldSlot may be recorded and transcribed to prepare a summary for
        the host. Prospects are shown a recording notice before booking and can ask the host to stop
        recording at any time.
      </p>

      <h2>4 · Sharing</h2>
      <p>
        We share data only with the service providers needed to run a campaign (sourcing, sending,
        calendar, and AI processing) and with the client the campaign is run for. We do not sell
        personal data.
      </p>

      <h2>5 · Your choices</h2>
      <p>
        Recipients can unsubscribe or request not to be contacted at any time, and we honour
        do-not-contact requests permanently. To access, correct, or delete data, contact{" "}
        <a href="mailto:privacy@holdslot.com">privacy@holdslot.com</a>.
      </p>

      <h2>6 · Retention &amp; security</h2>
      <p>
        We keep data only as long as needed to run campaigns and meet legal obligations, and protect
        it with access controls and encryption in transit.
      </p>
    </LegalPage>
  );
}
