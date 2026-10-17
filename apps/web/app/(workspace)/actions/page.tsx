import Link from "next/link";
import { ActionShell, ServiceUnavailable } from "@/components/action-shell";
import { ActionStateBadge, StateGuidance } from "@/components/action-state";
import type { ActionRecord } from "@/lib/action-types";
import { readActionData } from "@/lib/action-server";

export default async function ActionsPage() {
  const { data } = await readActionData<{ actions: ActionRecord[] }>("/actions");
  return (
    <ActionShell eyebrow="Control plane / immutable ledger" title="Action ledger">
      {!data ? <ServiceUnavailable /> : data.actions.length === 0 ? (
        <div className="empty-panel"><strong>No actions recorded</strong><p>The ledger is independent from chat history and browser storage.</p></div>
      ) : (
        <div className="action-list">
          {data.actions.map((action) => (
            <Link href={`/actions/${action.action_id}`} className="action-list__item" key={action.action_id}>
              <div><span>{action.payload_json.target.company}</span><h2>{action.payload_json.parameters.title}</h2><code>{action.action_id}</code></div>
              <div className="action-list__status"><ActionStateBadge state={action.state} /><span>rev {action.current_revision}</span></div>
              <StateGuidance state={action.state} />
            </Link>
          ))}
        </div>
      )}
    </ActionShell>
  );
}
