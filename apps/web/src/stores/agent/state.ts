import type { AgentId } from "@/interfaces/app";
import type { AgentConfig, ChatThread, Skill, ThreadDetail } from "@/interfaces/agent";
import { create } from "zustand";
import { useAuthStore } from "@/stores/auth";
import { writeAccountCache } from "@/lib/account-storage";

export type State = {
  owner: number | null;
  agents: AgentConfig[];
  partnerCodes: AgentId[];
  skills: Skill[];
  loading: boolean;
  error: string | null;
  lists: Partial<Record<AgentId, ChatThread[]>>;
  selected: Partial<Record<AgentId, string | null>>;
  details: Record<string, ThreadDetail>;
  /** 会话正在生成回复（发送中）状态，按会话 id 索引 */
  sending: Record<string, boolean>;
  configBusy: boolean;
  switching: boolean;
};
const empty = (): State => ({
  owner: null,
  agents: [],
  partnerCodes: [],
  skills: [],
  loading: false,
  error: null,
  lists: {},
  selected: {},
  details: {},
  sending: {},
  configBusy: false,
  switching: false,
});
export const useAgentStore = create<State>(() => empty());

/** 共享运行时状态（发送流、请求去重、登录代际） */
export const bootstrapRef: { current: Promise<void> | null } = { current: null };
export const generationRef: { current: number } = { current: 0 };
export const runs = new Map<string, AbortController>();
export const runIds = new Map<string, string>();
export const stops = new Map<string, Promise<void>>();
export const titleRequests = new Map<string, Promise<string | undefined>>();
export const timers = new Map<string, ReturnType<typeof setTimeout>>();
export const creates = new Map<string, Promise<string>>();
export const createIds = new Map<string, string>();
export const mutations = new Map<string, Promise<unknown>>();
export const removed = new Set<string>();
export const message = (error: unknown) =>
  error instanceof Error ? error.message : "操作失败，请重试。";

export function currentOwner() {
  const owner = useAuthStore.getState().user?.id;
  if (!owner || useAgentStore.getState().owner !== owner)
    throw new Error("登录状态已改变，请重试。");
  return owner;
}
export function owned(owner: number) {
  return useAuthStore.getState().user?.id === owner && useAgentStore.getState().owner === owner;
}
export function resetAgents() {
  generationRef.current++;
  bootstrapRef.current = null;
  for (const controller of runs.values()) controller.abort();
  runs.clear();
  runIds.clear();
  stops.clear();
  titleRequests.clear();
  mutations.clear();
  removed.clear();
  creates.clear();
  createIds.clear();
  for (const timer of timers.values()) clearTimeout(timer);
  timers.clear();
  useAgentStore.setState(empty());
}

/** 串行提交同一会话的请求，避免自身请求产生版本冲突。 */
export function mutate<T>(owner: number, id: string, operation: () => Promise<T>): Promise<T> {
  const key = `${owner}:${id}`;
  const version = generationRef.current;
  const previous = mutations.get(key) ?? Promise.resolve();
  const next = (async () => {
    try {
      await previous;
    } catch {
      // 忽略上一次失败，继续执行本次操作
    }
    if (!owned(owner) || version !== generationRef.current || removed.has(key))
      throw new Error("会话已关闭或登录状态已改变。");
    return operation();
  })();
  mutations.set(key, next);
  void (async () => {
    try {
      await next;
    } catch {
      // 错误已由调用方处理，这里只做清理
    } finally {
      if (mutations.get(key) === next) mutations.delete(key);
    }
  })();
  return next;
}

export function updateList(state: State, code: AgentId, thread: ChatThread) {
  const previous = state.lists[code]?.find((row) => row.id === thread.id);
  thread = { ...thread, has_history: thread.has_history ?? previous?.has_history ?? false };
  return {
    ...state.lists,
    [code]: [thread, ...(state.lists[code] ?? []).filter((row) => row.id !== thread.id)].sort(
      (a, b) => b.updated_at.localeCompare(a.updated_at),
    ),
  };
}

export function remember(owner: number, code: AgentId, detail: ThreadDetail) {
  detail = {
    ...detail,
    thread: {
      ...detail.thread,
      has_history:
        detail.thread.has_history ??
        [...detail.messages, ...(detail.message_branches ?? []).map((entry) => entry.message)].some(
          (row) => row.role === "assistant" && row.status === "complete" && row.content.trim(),
        ),
    },
  };
  if (!owned(owner) || removed.has(`${owner}:${detail.thread.id}`)) return;
  useAgentStore.setState((state) => {
    const previous = state.details[detail.thread.id];
    if (previous && previous.thread.draft_revision > detail.thread.draft_revision) return state;
    return {
      lists: updateList(state, code, detail.thread),
      details: { ...state.details, [detail.thread.id]: detail },
    };
  });
}

export async function persistGraph(code: AgentId, id: string) {
  const owner = currentOwner();
  const snapshot = useAgentStore.getState().details[id];
  if (!snapshot) throw new Error("会话不存在。");
  const { saveConversationMessages } = await import("@/apis/conversations");
  return mutate(owner, id, async () => {
    const detail = useAgentStore.getState().details[id];
    if (!detail) throw new Error("会话不存在。");
    const saved = await saveConversationMessages(id, { ...snapshot, thread: detail.thread });
    if (!owned(owner) || removed.has(`${owner}:${id}`)) return;
    const current = useAgentStore.getState().details[id];
    if (
      current.messages === snapshot.messages &&
      current.message_branches === snapshot.message_branches
    )
      remember(owner, code, saved);
    else
      useAgentStore.setState((state) => ({
        lists: updateList(state, code, saved.thread),
        details: { ...state.details, [id]: { ...state.details[id], thread: saved.thread } },
      }));
  });
}

useAgentStore.subscribe((state, previous) => {
  if (
    !state.owner ||
    !state.agents.length ||
    (state.agents === previous.agents &&
      state.selected === previous.selected &&
      state.partnerCodes === previous.partnerCodes)
  )
    return;
  // 本地保存 Agent 配置、已添加伙伴和当前选择；正文由 Sidecar 本地保存。
  try {
    writeAccountCache(`agent-config:${state.owner}`, {
      agents: state.agents,
      partner_codes: state.partnerCodes,
      skills: state.skills,
      selected: state.selected,
    });
  } catch {
    /* 配置缓存不可用时不影响服务端会话。 */
  }
});
