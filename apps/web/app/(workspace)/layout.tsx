import { MyRuntimeProvider } from "@/app/MyRuntimeProvider";

export default function WorkspaceLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <>
      {process.env.OPERION_ENVIRONMENT === "enterprise" ? (
        <a href="/session" className="gateway-session-link">Session / sign out</a>
      ) : null}
      <MyRuntimeProvider>{children}</MyRuntimeProvider>
    </>
  );
}
