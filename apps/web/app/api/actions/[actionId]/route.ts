import { actionServerFetch } from "@/lib/action-server";

export async function GET(
  _request: Request,
  context: { params: Promise<{ actionId: string }> },
) {
  const { actionId } = await context.params;
  const response = await actionServerFetch(`/actions/${encodeURIComponent(actionId)}`);
  return new Response(response.body, {
    status: response.status,
    headers: { "Content-Type": "application/json" },
  });
}
