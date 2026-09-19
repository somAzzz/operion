const upstream = () =>
  process.env.OPERION_AGENT_URL ?? "http://127.0.0.1:8000/api/agent";

export async function POST(request: Request) {
  const token = process.env.OPERION_AGENT_TOKEN;
  if (!token) return new Response("Agent service is not configured.", { status: 503 });
  const response = await fetch(upstream(), {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
      Accept: "text/event-stream",
      "Content-Type": request.headers.get("content-type") ?? "application/json",
    },
    body: request.body,
    duplex: "half",
    signal: request.signal,
  } as RequestInit & { duplex: "half" });
  return new Response(response.body, {
    status: response.status,
    headers: {
      "Content-Type": response.headers.get("content-type") ?? "text/event-stream",
      "Cache-Control": "no-cache, no-transform",
    },
  });
}
