import { actionServerFetch } from "@/lib/action-server";

export async function GET(request: Request) {
  const status = new URL(request.url).searchParams.get("status");
  const path = status ? `/actions?status=${encodeURIComponent(status)}` : "/actions";
  const response = await actionServerFetch(path);
  return new Response(response.body, {
    status: response.status,
    headers: { "Content-Type": "application/json" },
  });
}
