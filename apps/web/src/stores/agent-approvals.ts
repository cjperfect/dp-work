import { create } from "zustand";
import { listAgentApprovals, type AgentApproval } from "@/apis/agent-approvals";
import { getAccessToken, useAuthStore } from "@/stores/auth";

type Entry = { items: AgentApproval[]; loading: boolean; error: string | null };
export const useAgentApprovalStore = create<{ entries: Record<string, Entry> }>(() => ({
  entries: {},
}));
const pending = new Map<string, Promise<void>>();
let generation = 0;
useAuthStore.subscribe((state, previous) => {
  if (state.user?.id !== previous.user?.id) {
    generation++;
    pending.clear();
    useAgentApprovalStore.setState({ entries: {} });
  }
});

/** 事件触发后刷新；页面重新打开时从 PG 恢复，不使用轮询。 */
export async function loadApprovals(threadId: string, force = false): Promise<void> {
  const token = getAccessToken();
  if (!token) return;
  const version = generation;
  const key = `${version}:${token}:${threadId}`;
  const running = pending.get(key);
  if (running) {
    await running;
    if (force && version === generation && token === getAccessToken())
      return loadApprovals(threadId);
    return;
  }
  useAgentApprovalStore.setState((state) => ({
    entries: {
      ...state.entries,
      [threadId]: { items: state.entries[threadId]?.items ?? [], loading: true, error: null },
    },
  }));
  const owned = () => version === generation && token === getAccessToken();
  const operation = listAgentApprovals(threadId)
    .then((items) => {
      if (owned())
        useAgentApprovalStore.setState((state) => ({
          entries: { ...state.entries, [threadId]: { items, loading: false, error: null } },
        }));
    })
    .catch((cause: unknown) => {
      if (owned())
        useAgentApprovalStore.setState((state) => ({
          entries: {
            ...state.entries,
            [threadId]: {
              items: state.entries[threadId]?.items ?? [],
              loading: false,
              error: cause instanceof Error ? cause.message : "审批加载失败",
            },
          },
        }));
    })
    .finally(() => {
      if (pending.get(key) === operation) pending.delete(key);
    });
  pending.set(key, operation);
  return operation;
}
