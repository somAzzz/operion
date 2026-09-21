import Link from "next/link";
import type { ReactNode } from "react";
import { ArrowLeftIcon, CheckCircle2Icon, ListChecksIcon } from "lucide-react";

export function ActionShell({
  eyebrow,
  title,
  children,
}: {
  eyebrow: string;
  title: string;
  children: ReactNode;
}) {
  return (
    <main className="action-page">
      <header className="action-page__header">
        <Link href="/" className="back-link">
          <ArrowLeftIcon aria-hidden="true" /> Evidence desk
        </Link>
        <nav aria-label="Action control">
          <Link href="/approvals"><CheckCircle2Icon aria-hidden="true" />Approvals</Link>
          <Link href="/actions"><ListChecksIcon aria-hidden="true" />Actions</Link>
        </nav>
      </header>
      <section className="action-page__intro">
        <p>{eyebrow}</p>
        <h1>{title}</h1>
      </section>
      {children}
    </main>
  );
}

export function ServiceUnavailable() {
  return (
    <div className="empty-panel" role="status">
      <strong>Action data is temporarily unavailable</strong>
      <p>No decision was sent. Refresh this page or try again later.</p>
    </div>
  );
}
