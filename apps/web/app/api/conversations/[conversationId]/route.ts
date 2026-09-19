export async function GET(
  _request: Request,
  context: { params: Promise<{ conversationId: string }> },
) {
  const token = process.env.OPERION_AGENT_TOKEN;
  if (!token) return new Response("Agent service is not configured.", { status: 503 });
  const { conversationId } = await context.params;
  const base = process.env.OPERION_AGENT_URL ?? "http://127.0.0.1:8000/api/agent";
  const url = new URL(`conversations/${encodeURIComponent(conversationId)}`, base.replace(/agent$/, ""));
  const response = await fetch(url, {
    headers: { Authorization: `Bearer ${token}` },
    cache: "no-store",
  });
  return new Response(response.body, {
    status: response.status,
    headers: { "Content-Type": "application/json" },
  });
}
