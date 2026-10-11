import "server-only";
import { context, propagation } from "@opentelemetry/api";

/** Forward only the active server trace; never propagate arbitrary baggage. */
export function upstreamTraceHeaders(input?: HeadersInit): Headers {
  const headers = new Headers(input);
  if (process.env.OPERION_OTEL_ENABLED === "1") {
    propagation.inject(context.active(), headers, {
      set(carrier: Headers, key: string, value: string) {
        carrier.set(key, value);
      },
    });
  }
  headers.delete("baggage");
  return headers;
}
