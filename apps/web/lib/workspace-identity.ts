import "server-only";

import { cache } from "react";
import { upstreamAuthorization } from "@/lib/upstream-auth";
import { upstreamTraceHeaders } from "@/lib/trace-headers";
import { navigationAccess } from "@/lib/navigation-access";

/** Per-render cache only; no user identity or role state is shared across users. */
export const workspaceAccess = cache(async () => {
  const denied = navigationAccess([]);
  const authorization = await upstreamAuthorization(process.env.OPERION_AGENT_TOKEN);
  if (!authorization) return denied;
  try {
    const base = process.env.OPERION_AGENT_URL ?? "http://127.0.0.1:8000/api/agent";
    const response = await fetch(new URL("/api/identity", base), {
      headers: upstreamTraceHeaders({ Authorization: authorization }),
      cache: "no-store",
      signal: AbortSignal.timeout(5000),
    });
    if (!response.ok) return denied;
    const identity: unknown = await response.json();
    return navigationAccess(
      identity && typeof identity === "object" && "roles" in identity
        ? identity.roles
        : undefined,
    );
  } catch {
    return denied;
  }
});
