import { DeliveryComplaint } from "@/components/delivery-complaint";

export default async function ComplaintsPage({ searchParams }: {
  searchParams: Promise<{ round?: string }>;
}) {
  const { round } = await searchParams;
  return <DeliveryComplaint key={round ?? "current"} round={round} />;
}
