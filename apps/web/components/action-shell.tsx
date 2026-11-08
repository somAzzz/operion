import type { ReactNode } from "react";
import { EvidenceDeskLink, WorkspaceNavigation } from "@/components/workspace-navigation";

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
        <EvidenceDeskLink />
        <nav aria-label="Action control">
          <WorkspaceNavigation icons />
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
