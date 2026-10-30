import type { AgentApproval } from "@/interfaces/agent";
import { useEffect, useRef, useState } from "react";
import { useAuiState } from "@assistant-ui/react";
import { ApprovalCard } from "@/components/assistant-ui/elements/approval-card";
import { Button } from "@/components/ui/button";
import { loadApprovals, useAgentApprovalStore } from "@/stores/agent/agent-approvals";
import { resumeApprovedRun, useAgentStore } from "@/stores/agent";
import { useAuthStore } from "@/stores/auth";

/** 从本机恢复待执行审批，提交期间锁定按钮，失败保留重试入口。 */
export function AgentApprovals() {
  const id = useAuiState((s) => s.threadListItem.remoteId);
  const owner = useAuthStore((s) => s.user?.id);
  const entry = useAgentApprovalStore((s) => (id ? s.entries[id] : undefined));
  const sending = useAgentStore((s) => (id ? s.sending[id] : false));
  const identity = useRef("");
  identity.current = `${owner}:${id}`;
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    setError(null);
    setBusy(null);
    if (id && owner) void loadApprovals(id);
  }, [id, owner]);
  async function answer(approval: AgentApproval, decision: "approve" | "reject") {
    if (busy || sending) return;
    const target = identity.current;
    setBusy(approval.id);
    setError(null);
    try {
      await resumeApprovedRun(approval, decision);
    } catch (cause) {
      if (identity.current === target)
        setError(cause instanceof Error ? cause.message : "审批提交失败，请重试。");
    } finally {
      if (identity.current === target) setBusy(null);
    }
  }
  const pending =
    entry?.items.filter((approval) => approval.actionable && approval.id !== busy) ?? [];
  if (!id || (!pending.length && !entry?.error && !error)) return null;
  return (
    <div
      data-slot="agent-approvals"
      className="max-h-[45vh] overflow-y-auto overscroll-contain rounded-t-(--composer-radius) border border-b-0 border-foreground/10 bg-card [&>section+section]:border-t [&>p]:px-4 [&>p]:py-2 [&>button]:m-3"
      aria-label="工具审批"
    >
      {pending.map((approval) => (
        <ApprovalCard
          key={approval.id}
          className="rounded-none border-0 shadow-none"
          state="request"
          title="工具执行审批"
          subtitle="以下操作尚未执行，允许后才会继续；此前完成的步骤不会重做"
          disabled={!!busy || !!sending || !!entry?.loading}
          details={approval.interrupts
            .flatMap((interrupt) => interrupt.value.action_requests)
            .map((action, index) => ({
              label: `${({ execute: "执行命令", write_file: "写入文件", edit_file: "修改文件" } as Record<string, string>)[action.name] ?? action.name} · ${index + 1}`,
              value: JSON.stringify(action.args, null, 2),
            }))}
          onAllowOnce={() => void answer(approval, "approve")}
          onDeny={() => void answer(approval, "reject")}
        />
      ))}
      {(error || entry?.error) && (
        <p role="alert" className="text-sm text-destructive">
          {error ?? entry?.error}
        </p>
      )}
      {(error || entry?.error) && (
        <Button
          size="sm"
          variant="outline"
          className="justify-self-start"
          onClick={() => {
            setError(null);
            void loadApprovals(id, true);
          }}
        >
          重新加载审批
        </Button>
      )}
    </div>
  );
}
