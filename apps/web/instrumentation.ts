export async function register() {
  if (process.env.OPERION_OTEL_ENABLED !== "1") return;
  const { registerOTel } = await import("@vercel/otel");
  const { businessTraceSampler, telemetryAttributes } = await import("./lib/telemetry");
  registerOTel({
    serviceName: "operion-web",
    attributes: telemetryAttributes(),
    traceSampler: businessTraceSampler,
  });
}
