import "server-only";

import { cookies, headers } from "next/headers";

export async function upstreamAuthorization(localToken?: string) {
  if (process.env.OPERION_ENVIRONMENT !== "enterprise") {
    return localToken ? `Bearer ${localToken}` : null;
  }
  const requestHeaders = await headers();
  const forwarded = requestHeaders.get("x-forwarded-access-token");
  const cookieName = process.env.OPERION_ACCESS_TOKEN_COOKIE ?? "operion_access_token";
  const cookieToken = (await cookies()).get(cookieName)?.value;
  const token = forwarded ?? cookieToken;
  return token ? `Bearer ${token}` : null;
}
