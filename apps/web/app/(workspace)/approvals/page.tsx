import { ActionShell, ServiceUnavailable } from "@/components/action-shell";
import { ApprovalList } from "@/components/approval-list";
import type { ActionRecord } from "@/lib/action-types";
import { readActionData } from "@/lib/action-server";

export default async function ApprovalsPage() {
  const { data } = await readActionData<{ actions: ActionRecord[] }>(
    "/actions?status=PENDING_APPROVAL",
  );
  return (
    <ActionShell eyebrow="Control plane / trusted decision" title="Pending approvals">
      {data ? <ApprovalList initialActions={data.actions} /> : <ServiceUnavailable />}
    </ActionShell>
  );
}
