"use client";

import { createContext, useContext, type ReactNode } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  CheckCircle2,
  Inbox,
  Layers3,
  ListChecks,
  MessageSquareText,
  UserRound,
} from "lucide-react";
import {
  navigationAccess,
  type NavigationAccess,
} from "@/lib/navigation-access";

const AccessContext = createContext<NavigationAccess>(navigationAccess([]));

export function WorkspaceAccessProvider({
  access,
  children,
}: {
  access: NavigationAccess;
  children: ReactNode;
}) {
  return (
    <AccessContext.Provider value={access}>{children}</AccessContext.Provider>
  );
}

export function ActionLink({
  destination,
  className,
  children,
}: {
  destination: "actions" | "approvals";
  className?: string;
  children: ReactNode;
}) {
  const access = useContext(AccessContext);
  if (!access[destination]) return null;
  return (
    <Link href={`/${destination}`} prefetch={false} className={className}>
      {children}
    </Link>
  );
}

const destinations = [
  {
    href: "/",
    label: "Inquiry",
    permission: "evidence",
    Icon: MessageSquareText,
  },
  {
    href: "/complaints",
    label: "Complaints",
    permission: "evidence",
    Icon: Inbox,
  },
  {
    href: "/approvals",
    label: "Approvals",
    permission: "approvals",
    Icon: CheckCircle2,
  },
  {
    href: "/actions",
    label: "Actions",
    permission: "actions",
    Icon: ListChecks,
  },
] as const;

export function WorkspaceBar({ enterprise }: { enterprise: boolean }) {
  const access = useContext(AccessContext);
  const pathname = usePathname();
  return (
    <header className="workspace-bar">
      <div className="workspace-brand">
        <span className="brand-symbol">
          <Layers3 aria-hidden="true" />
        </span>
        <strong>Operion</strong>
        <span className="brand-product">Evidence desk</span>
      </div>
      <nav aria-label="Workspace">
        {destinations
          .filter((item) => access[item.permission])
          .map(({ href, label, Icon }) => {
            const current =
              pathname === href ||
              (href !== "/" && pathname.startsWith(href + "/"));
            return (
              <Link
                key={href}
                href={href}
                prefetch={false}
                aria-current={current ? "page" : undefined}
              >
                <Icon aria-hidden="true" />
                {label}
              </Link>
            );
          })}
      </nav>
      {enterprise && (
        <Link
          className="session-link"
          href="/session"
          aria-label="Session / sign out"
          aria-current={pathname === "/session" ? "page" : undefined}
        >
          <UserRound aria-hidden="true" />
          <span>Session</span>
        </Link>
      )}
    </header>
  );
}
