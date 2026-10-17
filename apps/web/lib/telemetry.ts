import { trace, TraceFlags } from "@opentelemetry/api";
import type { Configuration } from "@vercel/otel";

type Sampler = Exclude<NonNullable<Configuration["traceSampler"]>, string>;

/** Drop health-check trees at the root, preserving normal parent decisions. */
export const businessTraceSampler: Sampler = {
  shouldSample(parentContext, _traceId, _name, _kind, attributes) {
    const target = attributes["http.target"] ?? attributes["url.path"] ?? attributes["http.route"];
    if (typeof target === "string" && target.split("?")[0] === "/health") {
      return { decision: 0 };
    }
    const parent = trace.getSpanContext(parentContext);
    return { decision: parent && !(parent.traceFlags & TraceFlags.SAMPLED) ? 0 : 2 };
  },
  toString: () => "OperionBusinessTraceSampler",
};

export function telemetryAttributes() {
  const environment = process.env.OPERION_TELEMETRY_ENVIRONMENT ??
    process.env.OPERION_ENVIRONMENT ?? "local";
  const release = process.env.OPERION_RELEASE_ID ?? "dev";
  return {
    "service.version": release,
    "deployment.environment.name": environment,
    "langfuse.environment": environment,
    "langfuse.release": release,
    "langfuse.version": release,
  };
}
