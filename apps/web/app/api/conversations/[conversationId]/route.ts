import { upstreamAuthorization } from "@/lib/upstream-auth";

export async function GET(
  _request: Request,
  context: { params: Promise<{ conversationId: string }> },
) {
  const token = process.env.OPERION_AGENT_TOKEN;
  const authorization = await upstreamAuthorization(token);
  if (!authorization) return new Response("Authentication is required.", { status: 401 });
  const { conversationId } = await context.params;
  const base = process.env.OPERION_AGENT_URL ?? "http://127.0.0.1:8000/api/agent";
  const url = new URL(`conversations/${encodeURIComponent(conversationId)}`, base.replace(/agent$/, ""));
  const response = await fetch(url, {
    headers: { Authorization: authorization },
    cache: "no-store",
  });
  return new Response(response.body, {
    status: response.status,
    headers: { "Content-Type": "application/json" },
  });
}

export async function DELETE(
  request: Request,
  context: { params: Promise<{ conversationId: string }> },
) {
  if (request.headers.get("x-operion-intent") !== "delete-conversation") {
    return Response.json(
      { error: { detail: "Missing conversation deletion intent." } },
      { status: 403 },
    );
  }
  const token = process.env.OPERION_AGENT_TOKEN;
  const authorization = await upstreamAuthorization(token);
  if (!authorization) {
    return new Response("Authentication is required.", { status: 401 });
  }
  const { conversationId } = await context.params;
  const base = process.env.OPERION_AGENT_URL ?? "http://127.0.0.1:8000/api/agent";
  const url = new URL(
    `conversations/${encodeURIComponent(conversationId)}`,
    base.replace(/agent$/, ""),
  );
  const response = await fetch(url, {
    method: "DELETE",
    headers: {
      Authorization: authorization,
      "X-Operion-Intent": "delete-conversation",
    },
    cache: "no-store",
  });
  return new Response(response.body, {
    status: response.status,
    headers: { "Content-Type": "application/json" },
  });
}
