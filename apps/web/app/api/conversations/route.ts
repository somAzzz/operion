import { upstreamAuthorization } from "@/lib/upstream-auth";

export async function GET() {
  const token = process.env.OPERION_AGENT_TOKEN;
  const authorization = await upstreamAuthorization(token);
  if (!authorization) {
    return new Response("Authentication is required.", { status: 401 });
  }
  const base = process.env.OPERION_AGENT_URL ?? "http://127.0.0.1:8000/api/agent";
  const url = new URL("conversations", base.replace(/agent$/, ""));
  const response = await fetch(url, {
    headers: { Authorization: authorization },
    cache: "no-store",
  });
  return new Response(response.body, {
    status: response.status,
    headers: { "Content-Type": "application/json" },
  });
}
