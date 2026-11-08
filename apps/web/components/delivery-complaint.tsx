"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { useAui, useAuiState } from "@assistant-ui/react";
import { ArrowRight, ClipboardList, FileText, Inbox, Mail, MessagesSquare } from "lucide-react";
import { MyRuntimeProvider } from "@/app/MyRuntimeProvider";
import { Thread } from "@/components/assistant-ui/elements/thread.aui";
import { WorkspaceNavigation } from "@/components/workspace-navigation";

type CaseFile = {
  round_number: number; latest_round: number;
  thread_id: string; note_id: string; order_id: string; company_id: string;
  company: string; claim: string; sender: {status: string; id?: string; name?: string; email?: string};
  email_read: boolean; unavailable: boolean;
  review: null | { draft: string; records: {kind: "issue" | "invoice"; id: number; detail: string}[] };
};

export function DeliveryComplaint({ round }: { round?: string }) {
  const [file, setFile] = useState<CaseFile | null>(null);
  const [error, setError] = useState("");
  const refresh = useCallback(async (signal?: AbortSignal) => {
    try {
      const params = new URLSearchParams({ desk: "1" });
      if (round !== undefined) params.set("round_number", round);
      const response = await fetch("/api/delivery-complaint?" + params, { cache: "no-store", signal });
      if (!response.ok) throw new Error(response.status === 404 || response.status === 403
        ? "No complaint available in your scope." : "The complaint could not be loaded.");
      const data: CaseFile = await response.json();
      if (!signal?.aborted) { setFile(data); setError(""); }
    } catch (err) {
      if (!signal?.aborted) { setFile(null); setError(err instanceof Error ? err.message : "Complaint unavailable."); }
    }
  }, [round]);
  useEffect(() => {
    const controller = new AbortController();
    void refresh(controller.signal);
    return () => controller.abort();
  }, [refresh]);
  if (!file) return <main className="case-empty"><Link href="/">← Inquiry</Link><h1>Complaints</h1>
    <p role="status">{error || "Loading complaint…"}</p>{error && <button onClick={() => refresh()}>Retry</button>}</main>;
  return <MyRuntimeProvider key={file.thread_id} fixedThreadId={file.thread_id}>
    <ComplaintDesk file={file} refresh={refresh} />
  </MyRuntimeProvider>;
}

function ComplaintDesk({file, refresh}: {file: CaseFile; refresh: () => Promise<void>}) {
  const aui = useAui();
  const running = useAuiState(s => s.thread.isRunning);
  const router = useRouter();
  const inquiry = useSearchParams().get("view") === "inquiry";
  const [pending, setPending] = useState(false);
  const [starting, setStarting] = useState(false);
  const [startError, setStartError] = useState("");
  const active = useRef(false);
  useEffect(() => {
    if (running) { active.current = true; return; }
    if (active.current) {
      active.current = false;
      setPending(true);
      void refresh().finally(() => setPending(false));
    }
  }, [running, refresh]);
  const busy = running || pending || starting;
  const review = busy ? null : file.review;
  const base = "/orders/" + file.order_id;
  const note = encodeURIComponent(file.note_id);
  const companyUrl = base + "?open=company&record=" + file.company_id + "&note=" + note;
  const complaintUrl = "/complaints?round=" + file.round_number;
  async function startInvestigation() {
    setStarting(true);
    setStartError("");
    try {
      const response = await fetch("/api/delivery-complaint?after=" + encodeURIComponent(file.thread_id), {
        method: "POST", headers: { "X-Operion-Intent": "start-investigation" },
      });
      if (!response.ok) throw new Error(response.status === 409
        ? "Another investigation has started. Reopen Complaints to see the current round."
        : "Could not start a new investigation. Please try again.");
      const next: CaseFile = await response.json();
      router.push("/complaints?round=" + next.round_number);
    } catch (error) {
      setStartError(error instanceof Error ? error.message : "Could not start a new investigation.");
      setStarting(false);
    }
  }
  return <main className="case-desk">
    <aside className="case-rail">
      <p>OPERION</p><h1>Evidence desk</h1>
      <nav aria-label="Workspace">
        <Link href="/complaints" aria-current={!inquiry ? "page" : undefined}><Inbox/>Complaints</Link>
        <Link href="/"><MessagesSquare/>Inquiry</Link><WorkspaceNavigation />
      </nav>
    </aside>
    <section className="case-main">
      <header className="case-header"><div className="case-path">Complaints <span>/</span> Order {file.order_id}</div>
        <h2>{inquiry ? "Order inquiry" : "Delivery complaint"} <span>· {file.order_id}</span></h2>
        <a href={companyUrl} target="_blank" rel="noreferrer">{file.company}</a>
        {file.latest_round > 1 && <label className="case-round">Investigation
          <select value={file.round_number} disabled={busy} onChange={event => router.push("/complaints?round=" + event.target.value)}>
            {Array.from({ length: file.latest_round }, (_, i) => i + 1).reverse().map(number =>
              <option key={number} value={number}>Round {number}{number === file.latest_round ? " (current)" : ""}</option>)}
          </select>
        </label>}
      </header>
      {inquiry ? <><div className="case-tools"><Link href={complaintUrl}>← Back to complaint</Link>
        {review && <Link href={complaintUrl + "#case-review"}>Review draft →</Link>}
        </div>
        <div className="case-thread"><Thread autoFocus/></div></> :
      <><h3>Customer report</h3><article className="case-card">
        <div className="case-source"><Mail/> Customer email <a href={base + "?open=note&record=" + note} target="_blank" rel="noreferrer">Open in Twenty ↗</a></div>
        {file.email_read && <><p>From · {file.sender.status === "verified" ?
          <a href={base + "?open=sender&record=" + file.sender.id + "&note=" + note} target="_blank" rel="noreferrer">{file.sender.name} · {file.sender.email}</a> : "Sender pending confirmation"}</p>
          <blockquote>{file.claim}</blockquote></>}
        <div className="case-actions"><button className="case-primary" disabled={busy} onClick={() => file.email_read ? router.push(complaintUrl + "&view=inquiry") :
          aui.thread.append("Read Twenty Note " + file.note_id + ". What did the customer report in the email, who sent it and which company do they represent?")}>
          {busy ? "Working…" : !file.email_read ? "Read customer email" : review ? "Resume investigation" : file.unavailable ? "Retry investigation" : "Investigate order " + file.order_id}<ArrowRight/></button>
          {file.email_read && file.round_number === file.latest_round &&
            <button className="case-secondary" disabled={busy} onClick={startInvestigation}>Start new investigation</button>}
        </div>
        {startError && <p role="alert">{startError}</p>}
      </article>
      <h3>Investigation evidence</h3>
      {review ? review.records.map(record => <a className="case-card case-record" target="_blank" rel="noreferrer" key={record.kind + record.id}
        href={base + "/evidence/" + record.kind + "/" + record.id}><FileText/><div><strong>{record.kind === "issue" ? "Stock issue" : "Invoice"} {record.id} ↗</strong><p>{record.detail}</p></div></a>) :
        <p role="status">{busy ? "Updating investigation…" : file.unavailable ? "Delivery evidence unavailable. WWI could not be queried." : "Investigate the order to check its delivery records."}</p>}
      </>}
    </section>
    <aside id="case-review" tabIndex={-1} className="case-review" aria-label="Reply review">
      {review ? <><div className="case-pending"><ClipboardList/><strong>Human approval required</strong></div>
        <article className="case-card"><h3>Customer reply · Draft</h3><p>{review.draft}</p><div className="case-unsent">No email sent</div></article></> :
        <><ClipboardList/><h3>Customer reply</h3><p>{file.unavailable && !busy ? "Delivery evidence is unavailable. Retry the investigation before reviewing a reply." : "A draft will appear after delivery evidence has been checked."}</p></>}
    </aside>
  </main>;
}
