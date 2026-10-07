import Link from "next/link";
import { notFound } from "next/navigation";

export default function SessionPage() {
  if (process.env.OPERION_ENVIRONMENT !== "enterprise") notFound();
  return (
    <main className="action-page">
      <h1>Your session</h1>
      <p>Sign out to end this browser’s Operion session.</p>
      <form action="/oauth2/sign_out" method="post">
        <button type="submit" className="back-link">Sign out</button>
      </form>
      <Link href="/">Back to the evidence desk</Link>
    </main>
  );
}
