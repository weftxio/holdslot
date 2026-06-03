import Link from "next/link";
import "./legal.css";

export function LegalPage({
  title,
  updated,
  children,
}: {
  title: string;
  updated: string;
  children: React.ReactNode;
}) {
  return (
    <div className="legal">
      <header className="legal-top">
        <Link href="/" className="logo">
          <span className="dot" />
          HoldSlot
        </Link>
        <Link href="/" className="btn btn-ghost btn-sm">
          Back to home
        </Link>
      </header>

      <main className="legal-main">
        <h1>{title}</h1>
        <p className="updated">Last updated · {updated}</p>
        {children}
        <p className="legal-note">
          This is placeholder copy for the HoldSlot MVP and does not constitute legal advice. Final
          terms will be reviewed before launch.
        </p>
      </main>

      <footer className="legal-foot">
        <span>© 2026 HoldSlot</span>
        <span className="legal-links">
          <Link href="/privacy">Privacy</Link>
          <Link href="/terms">Terms</Link>
        </span>
      </footer>
    </div>
  );
}
