import { NextRequest, NextResponse } from "next/server";

function deny(request: NextRequest, status: number, message: string) {
  const page = !request.nextUrl.pathname.startsWith("/api/");
  // Messages are fixed application strings, never upstream error text or claims.
  return new NextResponse(page ? `<!doctype html><html lang="en"><title>Operion access</title>
    <h1>Operion access</h1><p>${message}</p>
    <form action="/oauth2/sign_out" method="post"><button>Sign out</button></form></html>` : message, {
    status,
    headers: {
      "Content-Type": page ? "text/html; charset=utf-8" : "text/plain; charset=utf-8",
      "Cache-Control": "no-store",
    },
  });
}

export async function proxy(request: NextRequest) {
  if (process.env.OPERION_ENVIRONMENT !== "enterprise") {
    return NextResponse.next();
  }
  // Network isolation establishes header provenance. The Python API separately
  // validates the JWT and resolves permissions for every backend request.
  if (!request.headers.get("x-forwarded-access-token")) {
    return deny(request, 401, "Authentication is required.");
  }
  const origin = process.env.OPERION_PUBLIC_ORIGIN;
  if (!origin || !URL.canParse(origin) || new URL(origin).protocol !== "https:") {
    return deny(request, 503, "Authentication is not configured.");
  }
  if (
    !["GET", "HEAD", "OPTIONS"].includes(request.method) &&
    request.headers.get("origin") !== origin
  ) {
    return deny(request, 403, "Same-origin request required.");
  }
  // Recheck current server policy even for pages, so disabled/unassigned users
  // do not enter the application with a still-valid gateway session.
  const agentUrl = process.env.OPERION_AGENT_URL;
  if (!agentUrl) {
    return deny(request, 503, "Authentication is not configured.");
  }
  try {
    const identity = await fetch(new URL("/api/identity", agentUrl), {
      headers: {
        Authorization: `Bearer ${request.headers.get("x-forwarded-access-token")}`,
      },
      cache: "no-store",
      signal: AbortSignal.timeout(5000),
    });
    if (!identity.ok) {
      const status = [401, 403].includes(identity.status) ? identity.status : 503;
      return deny(request, status, "Access is unavailable for this session.");
    }
    const current = await identity.json();
    const actionRoute = /^\/(api\/)?(actions|approvals)(\/|$)/.test(request.nextUrl.pathname);
    const sessionOrAsset = request.nextUrl.pathname === "/session" ||
      request.nextUrl.pathname.startsWith("/_next/") || request.nextUrl.pathname === "/favicon.ico";
    const allowedRoles = actionRoute
      ? ["action_reader", "action_approver", "action_operator"]
      : ["agent_read"];
    if (!Array.isArray(current.roles) || (!sessionOrAsset &&
      !current.roles.some((role: string) => allowedRoles.includes(role)))) {
      return deny(request, 403, "Your account cannot access this function.");
    }
  } catch {
    return deny(request, 503, "Authentication service is unavailable.");
  }
  const response = NextResponse.next();
  response.headers.set("Cache-Control", "no-store");
  return response;
}
