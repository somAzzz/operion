"use client";

import { InlineOrderText, OrderRecordsLink } from "@/components/order-records-link";
import { useAui, useAuiState } from "@assistant-ui/react";
import { useEffect, useState } from "react";

type Complaint = {
  order_id: string;
  company_id: string;
  note_id: string;
  company: string;
  title: string;
};

export function DeliveryComplaint() {
  const aui = useAui();
  const running = useAuiState((s) => s.thread.isRunning);
  const [note, setNote] = useState<Complaint | null>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    const controller = new AbortController();
    async function load() {
      const response = await fetch("/api/delivery-complaint", {
        cache: "no-store", signal: controller.signal,
      });
      if (response.status === 403 || response.status === 404) return;
      if (!response.ok) throw new Error("Complaint unavailable");
      setNote(await response.json());
    }
    load().catch(() => { if (!controller.signal.aborted) setFailed(true); });
    return () => controller.abort();
  }, []);
  if (failed) return <p role="status">Twenty complaint unavailable.</p>;
  if (!note) return null;
  return (
    <section className="complaint-entry" aria-label="Twenty complaint">
      <p className="rail-kicker">Twenty CRM · <a className="remote-link" target="_blank" rel="noopener noreferrer" href={`/orders/${note.order_id}?open=company&record=${note.company_id}&note=${note.note_id}`}>{note.company}</a></p>
      <h3><InlineOrderText text={note.title} /></h3>
      <p><a className="remote-link" target="_blank" rel="noopener noreferrer" href={`/orders/${note.order_id}?open=note&record=${note.note_id}`}>Open complaint note</a> · <OrderRecordsLink order={note.order_id} /></p>
      <button className="result-card__select" disabled={running}
        onClick={() => aui.thread.append(`Read Twenty Note ${note.note_id}. What did the customer report in the email, who sent it and which company do they represent?`)}>Read customer email</button>
    </section>
  );
}
