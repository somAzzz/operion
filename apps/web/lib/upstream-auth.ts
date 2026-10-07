import "server-only";

import { headers } from "next/headers";

export async function upstreamAuthorization(localToken?: string) {
  if (process.env.OPERION_ENVIRONMENT !== "enterprise") {
    return localToken ? `Bearer ${localToken}` : null;
  }
  const requestHeaders = await headers();
  const forwarded = requestHeaders.get("x-forwarded-access-token");
  // Only the trusted gateway supplies this header. OAuth tokens never live in
  // browser cookies; the gateway resolves its opaque session on the server.
  return forwarded ? `Bearer ${forwarded}` : null;
}
