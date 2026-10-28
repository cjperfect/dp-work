import { request } from "@/lib/http";
export type AgentApproval = {
  id: string;
  run_id: string;
  conversation_id: string;
  response_id: string;
  status: "pending" | "approved" | "rejected";
  actionable: boolean;
  interrupts: {
    id: string;
    value: {
      action_requests: { name: string; args: Record<string, unknown>; description?: string }[];
    };
  }[];
  created_at: string;
  decided_at: string | null;
};
export const listAgentApprovals = (threadId: string) =>
  request<AgentApproval[]>("/api/agents/approvals", { params: { conversation_id: threadId } });
