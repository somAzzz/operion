import { actionServerFetch } from "@/lib/action-server";

export async function POST(
  request: Request,
  context: { params: Promise<{ actionId: string }> },
) {
  if (request.headers.get("x-operion-intent") !== "decision") {
    return Response.json(
      { error: { detail: "Missing same-origin decision intent." } },
      { status: 403 },
    );
  }
  const csrf = process.env.OPERION_ACTION_CSRF_TOKEN;
  if (!csrf) {
    return Response.json(
      { error: { detail: "Action service is not configured." } },
      { status: 503 },
    );
  }
  const { actionId } = await context.params;
  const response = await actionServerFetch(
    `/actions/${encodeURIComponent(actionId)}/decisions`,
    {
      method: "POST",
      headers: { "X-Operion-CSRF": csrf },
      body: await request.text(),
    },
  );
  return new Response(response.body, {
    status: response.status,
    headers: { "Content-Type": "application/json" },
  });
}
