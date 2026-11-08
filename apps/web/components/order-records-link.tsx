import Link from "next/link";
import { orderMentions } from "@/lib/order-mentions";

export function OrderRecordsLink({ order }: { order: unknown }) {
  const id = typeof order === "string" && /^(?:wwi:sales_order:)?([1-9][0-9]{0,9})$/.exec(order)?.[1];
  if (!id || Number(id) > 2147483647) return null;
  return <Link href={`/orders/${id}`} prefetch={false} className="remote-link">Open order {id} records</Link>;
}

export function InlineOrderText({ text }: { text: string }) {
  return orderMentions(text).map((token, index) => token.type === "text" ? token.value : (
    <a key={index} href={token.url} target="_blank" rel="noopener noreferrer"
      className="remote-link" title="Open sales order in ERPNext">{token.children[0].value}</a>
  ));
}
