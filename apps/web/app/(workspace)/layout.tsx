import { WorkspaceAccessProvider } from "@/components/workspace-navigation";
import { workspaceAccess } from "@/lib/workspace-identity";

export default async function WorkspaceLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  const access = await workspaceAccess();
  return (
    <WorkspaceAccessProvider access={access}>
      {process.env.OPERION_ENVIRONMENT === "enterprise" ? (
        <a href="/session" className="gateway-session-link">Session / sign out</a>
      ) : null}
      {children}
    </WorkspaceAccessProvider>
  );
}
