import { upstreamAuthorization } from "@/lib/upstream-auth";
import { upstreamTraceHeaders } from "@/lib/trace-headers";

async function complaintRequest(request: Request) {
  const starting = request.method === "POST";
  if (starting && request.headers.get("x-operion-intent") !== "start-investigation") {
    return new Response("Missing investigation start intent.", { status: 403 });
  }
  const token = process.env.OPERION_AGENT_TOKEN;
  const authorization = await upstreamAuthorization(token);
  if (!authorization) {
    return new Response("Authentication is required.", { status: 401 });
  }
  const base = process.env.OPERION_AGENT_URL ?? "http://127.0.0.1:8000/api/agent";
  const url = new URL("delivery-complaint", base.replace(/agent$/, ""));
  const params = new URL(request.url).searchParams;
  if (params.get("desk") === "1") url.searchParams.set("desk", "true");
  const field = starting ? "after" : "round_number";
  if (params.has(field)) url.searchParams.set(field, params.get(field)!);
  const response = await fetch(url, {
    method: request.method,
    headers: upstreamTraceHeaders({
      Authorization: authorization,
      ...(starting ? { "X-Operion-Intent": "start-investigation" } : {}),
    }),
    cache: "no-store",
  });
  return new Response(response.body, {
    status: response.status,
    headers: { "Content-Type": "application/json" },
  });
}

export { complaintRequest as GET, complaintRequest as POST };
