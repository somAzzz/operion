export const SESSION_EXPIRED_MESSAGE =
  "Your session has expired or is no longer valid. Sign in again to continue.";
export const SESSION_EXPIRED_URL = "/login?reason=session_expired";

let redirectStarted = false;

/** One full navigation for concurrent 401s; preserve the active conversation. */
export function redirectToLogin(): void {
  if (typeof window === "undefined" || redirectStarted || window.location.pathname === "/login") {
    return;
  }
  redirectStarted = true;
  window.location.replace(SESSION_EXPIRED_URL);
}

/** Keep gateway 401s separate from model failures and business-policy denials. */
export async function fetchWithSession(
  input: RequestInfo | URL,
  init?: RequestInit,
  onUnauthorized: () => void = redirectToLogin,
): Promise<Response> {
  const response = await fetch(input, init);
  if (response.status === 401) {
    onUnauthorized();
    throw new Error(SESSION_EXPIRED_MESSAGE);
  }
  return response;
}
