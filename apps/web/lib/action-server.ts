import "server-only";
import { upstreamAuthorization } from "@/lib/upstream-auth";

const actionBase = () =>
  process.env.OPERION_ACTION_URL ?? "http://127.0.0.1:8001/api";

export async function actionServerFetch(path: string, init?: RequestInit) {
  const token = process.env.OPERION_ACTION_TOKEN;
  const authorization = await upstreamAuthorization(token);
  if (!authorization) {
    return new Response(JSON.stringify({ error: { detail: "Action service is not configured." } }), {
      status: 503,
      headers: { "Content-Type": "application/json" },
    });
  }
  return fetch(`${actionBase()}${path}`, {
    ...init,
    headers: {
      Authorization: authorization,
      ...(init?.body ? { "Content-Type": "application/json" } : {}),
      ...(init?.headers ?? {}),
    },
    cache: "no-store",
  });
}

export async function readActionData<T>(path: string): Promise<{
  data: T | null;
  status: number;
}> {
  try {
    const response = await actionServerFetch(path);
    return {
      data: response.ok ? ((await response.json()) as T) : null,
      status: response.status,
    };
  } catch {
    return { data: null, status: 503 };
  }
}
