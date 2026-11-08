import { WorkspaceAccessProvider, WorkspaceBar } from "@/components/workspace-navigation";
import { workspaceAccess } from "@/lib/workspace-identity";

export default async function WorkspaceLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  const access = await workspaceAccess();
  return (
    <WorkspaceAccessProvider access={access}>
      <div className="workspace">
        <WorkspaceBar enterprise={process.env.OPERION_ENVIRONMENT === "enterprise"} />
        {children}
      </div>
    </WorkspaceAccessProvider>
  );
}
