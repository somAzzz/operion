import type { Metadata } from "next";

export const metadata: Metadata = { title: "Sign in | Operion" };

export default async function LoginPage({
  searchParams,
}: {
  searchParams: Promise<{ reason?: string | string[] }>;
}) {
  const expired = (await searchParams).reason === "session_expired";
  return (
    <main className="login-page" lang="en">
      <section className="login-card" aria-labelledby="login-title">
        <p className="login-brand">OPERION</p>
        <h1 id="login-title">{expired ? "Sign in to Operion again" : "Sign in to Operion"}</h1>
        {expired ? (
          <div className="login-notice" role="status">
            <p>Your session has expired or is no longer valid. Please sign in again.</p>
          </div>
        ) : (
          <p>Sign in to continue to your authorized workspace.</p>
        )}
        <p className="login-help">Your saved conversations are retained. After signing in, you can view your history and resend any unfinished questions.</p>
        <form action="/oauth2/start" method="get">
          <input type="hidden" name="rd" value="/" />
          <button className="login-button" type="submit">{expired ? "Sign in again" : "Sign in"}</button>
        </form>
      </section>
    </main>
  );
}
