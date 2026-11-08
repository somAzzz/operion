import type { ReactNode } from "react";

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
