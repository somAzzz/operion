export async function register() {
  if (process.env.OPERION_OTEL_ENABLED !== "1") return;
  const { registerOTel } = await import("@vercel/otel");
  registerOTel({ serviceName: "operion-web" });
}
