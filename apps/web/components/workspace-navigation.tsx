"use client";

import { createContext, useContext, type ReactNode } from "react";
import Link from "next/link";
import { ArrowLeftIcon, CheckCircle2Icon, ListChecksIcon } from "lucide-react";
import { navigationAccess, type NavigationAccess } from "@/lib/navigation-access";

const AccessContext = createContext<NavigationAccess>(navigationAccess([]));

export function WorkspaceAccessProvider({
  access,
  children,
}: {
  access: NavigationAccess;
  children: ReactNode;
}) {
  return <AccessContext.Provider value={access}>{children}</AccessContext.Provider>;
}

/** No anchor is mounted for a denied destination, including in tool cards. */
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
  return <Link href={`/${destination}`} prefetch={false} className={className}>{children}</Link>;
}

export function WorkspaceNavigation({ icons = false }: { icons?: boolean }) {
  return (
    <>
      <ActionLink destination="approvals">{icons ? <CheckCircle2Icon aria-hidden="true" /> : null}Approvals</ActionLink>
      <ActionLink destination="actions">{icons ? <ListChecksIcon aria-hidden="true" /> : null}Actions</ActionLink>
    </>
  );
}

export function EvidenceDeskLink() {
  const access = useContext(AccessContext);
  if (!access.evidence) return null;
  return <Link href="/" prefetch={false} className="back-link"><ArrowLeftIcon aria-hidden="true" /> Evidence desk</Link>;
}
