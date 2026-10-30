import { create } from "zustand";
import { steerAgentRun } from "@/apis/agents";
import { useAuthStore } from "@/stores/auth";
import { getThreadAgentCode } from "./agent-threads";
import { sendMessage } from "./agent-send";
import { useAgentStore } from "./state";
import { useAgentApprovalStore } from "@/stores/agent/agent-approvals";

export type QueuedMessage = {
  id: string;
  text: string;
  images?: import("@/interfaces/agent").ChatImage[];
  mode?: "steering";
};
type QueueState = {
  owner: number | null;
  items: Record<string, QueuedMessage[]>;
  drafts: Record<string, string>;
  paused: Record<string, boolean>;
  errors: Record<string, string | null>;
};
export const useAgentMessageQueue = create<QueueState>(() => ({
  owner: null,
  items: {},
  drafts: {},
  paused: {},
  errors: {},
}));
const workers = new Map<string, Promise<void>>();
let generation = 0;

/** 仅保留尚未发送的消息和输入草稿，按账号隔离；刷新后等待用户继续。 */
export function initializeMessageQueue() {
  const owner = useAuthStore.getState().user?.id ?? null;
  if (useAgentMessageQueue.getState().owner === owner) return;
  generation++;
  const items: QueueState["items"] = {},
    drafts: QueueState["drafts"] = {};
  try {
    const saved = owner
      ? JSON.parse(localStorage.getItem(`dp-work:outbox:${owner}`) ?? "null")
      : null;
    if (saved && typeof saved === "object") {
      for (const [id, rows] of Object.entries(saved.items ?? {})) {
        if (Array.isArray(rows))
          items[id] = rows
            .filter(
              (row) =>
                row &&
                typeof row.id === "string" &&
                typeof row.text === "string" &&
                row.text.trim(),
            )
            .slice(0, 50)
            .map((row) => ({
              id: row.id,
              text: row.text,
              ...(Array.isArray(row.images) ? { images: row.images } : {}),
            }));
      }
      for (const [id, text] of Object.entries(saved.drafts ?? {}))
        if (typeof text === "string") drafts[id] = text;
    }
  } catch {
    /* 存储不可用时仍支持当前页面的排队。 */
  }
  workers.clear();
  useAgentMessageQueue.setState({
    owner,
    items,
    drafts,
    paused: Object.fromEntries(Object.keys(items).map((id) => [id, true])),
    errors: {},
  });
}
useAuthStore.subscribe((state, previous) => {
  if (state.user?.id !== previous.user?.id) initializeMessageQueue();
});
useAgentMessageQueue.subscribe((state) => {
  if (!state.owner) return;
  try {
    localStorage.setItem(
      `dp-work:outbox:${state.owner}`,
      JSON.stringify({ items: state.items, drafts: state.drafts }),
    );
  } catch {
    /* 不阻塞输入。 */
  }
});

export function saveComposerDraft(id: string, text: string) {
  initializeMessageQueue();
  useAgentMessageQueue.setState((state) => ({ drafts: { ...state.drafts, [id]: text } }));
}
export function waitingForApproval(id: string) {
  return (
    useAgentApprovalStore.getState().entries[id]?.items.some((row) => row.actionable) ||
    useAgentStore.getState().details[id]?.messages.some((row) => row.status === "waiting_approval")
  );
}
export function enqueueFollowUp(
  id: string,
  text: string,
  images?: import("@/interfaces/agent").ChatImage[],
) {
  initializeMessageQueue();
  if (!text.trim()) throw new Error("请输入消息。");
  if ((useAgentMessageQueue.getState().items[id]?.length ?? 0) >= 50)
    throw new Error("单个会话最多排队 50 条消息。");
  const row = { id: crypto.randomUUID(), text, ...(images?.length ? { images } : {}) };
  useAgentMessageQueue.setState((state) => ({
    items: { ...state.items, [id]: [...(state.items[id] ?? []), row] },
  }));
  void drainFollowUpQueue(id);
  return row.id;
}
export function removeQueuedMessage(id: string, messageId: string) {
  useAgentMessageQueue.setState((state) => ({
    items: { ...state.items, [id]: (state.items[id] ?? []).filter((row) => row.id !== messageId) },
  }));
}

/** 等上一次发送完成清理后再启动下一条，不并发提交同一会话。 */
export function drainFollowUpQueue(id: string): Promise<void> {
  const current = workers.get(id);
  if (current) return current;
  const owner = useAgentMessageQueue.getState().owner;
  const version = generation;
  const owned = () =>
    version === generation &&
    owner !== null &&
    owner === useAuthStore.getState().user?.id &&
    owner === useAgentStore.getState().owner;
  const operation = (async () => {
    while (owned()) {
      const state = useAgentMessageQueue.getState();
      if (state.paused[id] || useAgentStore.getState().sending[id] || waitingForApproval(id))
        return;
      const row = state.items[id]?.[0],
        code = getThreadAgentCode(id);
      if (!row || !code) return;
      removeQueuedMessage(id, row.id);
      try {
        await sendMessage(code, id, row.text, { images: row.images });
      } catch (cause) {
        if (owned())
          useAgentMessageQueue.setState((state) => ({
            items: { ...state.items, [id]: [row, ...(state.items[id] ?? [])] },
            paused: { ...state.paused, [id]: true },
            errors: {
              ...state.errors,
              [id]: cause instanceof Error ? cause.message : "消息发送失败",
            },
          }));
        return;
      }
      if (!owned()) return;
      const status = useAgentStore.getState().details[id]?.messages.at(-1)?.status;
      if (status !== "complete") {
        if (!waitingForApproval(id))
          useAgentMessageQueue.setState((state) => ({ paused: { ...state.paused, [id]: true } }));
        return;
      }
    }
  })();
  workers.set(id, operation);
  void operation
    .finally(() => {
      if (workers.get(id) === operation) workers.delete(id);
    })
    .catch(() => {});
  return operation;
}
export function continueMessageQueue(id: string) {
  useAgentMessageQueue.setState((state) => ({
    paused: { ...state.paused, [id]: false },
    errors: { ...state.errors, [id]: null },
  }));
  void drainFollowUpQueue(id);
}

/** 引导在同一运行的下一轮生效；没有活跃运行时才作为后续消息发送。 */
export async function guideQueuedMessage(id: string, messageId: string) {
  if (waitingForApproval(id)) throw new Error("请先处理当前工具审批。");
  const owner = useAgentMessageQueue.getState().owner,
    version = generation;
  const selected = useAgentMessageQueue.getState().items[id]?.find((row) => row.id === messageId);
  if (!selected || selected.mode === "steering") return;
  if (selected.images?.length) throw new Error("图片消息请等待当前回复完成后发送，暂不支持引导。");
  if (!useAgentStore.getState().sending[id]) {
    useAgentMessageQueue.setState((state) => ({
      items: {
        ...state.items,
        [id]: [selected, ...(state.items[id] ?? []).filter((row) => row.id !== messageId)],
      },
    }));
    continueMessageQueue(id);
    return;
  }
  useAgentMessageQueue.setState((state) => ({
    items: {
      ...state.items,
      [id]: (state.items[id] ?? []).map((row) =>
        row.id === messageId ? { ...row, mode: "steering" } : row,
      ),
    },
    errors: { ...state.errors, [id]: null },
  }));
  try {
    const result = await steerAgentRun(id, messageId, selected.text);
    if (owner !== useAuthStore.getState().user?.id || version !== generation) return;
    if (result.status === "applied") removeQueuedMessage(id, messageId);
  } catch (cause) {
    if (owner !== useAuthStore.getState().user?.id || version !== generation) return;
    useAgentMessageQueue.setState((state) => ({
      items: {
        ...state.items,
        [id]: (state.items[id] ?? []).map((row) =>
          row.id === messageId ? { id: row.id, text: row.text } : row,
        ),
      },
    }));
    throw cause;
  }
}

useAgentStore.subscribe((state, previous) => {
  for (const [id] of Object.entries(state.details)) {
    const messages = state.details[id]?.messages ?? [];
    if (messages.length !== previous.details[id]?.messages.length) {
      const applied = new Set(
        messages.filter((row) => row.context.steering_status === "applied").map((row) => row.id),
      );
      if (useAgentMessageQueue.getState().items[id]?.some((row) => applied.has(row.id))) {
        useAgentMessageQueue.setState((queue) => ({
          items: {
            ...queue.items,
            [id]: (queue.items[id] ?? []).filter((row) => !applied.has(row.id)),
          },
        }));
      }
    }
    if (previous.sending[id] && !state.sending[id]) {
      if (useAgentMessageQueue.getState().items[id]?.some((row) => row.mode)) {
        useAgentMessageQueue.setState((queue) => ({
          items: {
            ...queue.items,
            [id]: (queue.items[id] ?? []).map((row) => ({ id: row.id, text: row.text })),
          },
        }));
      }
      if (state.details[id]?.messages.at(-1)?.status === "complete") {
        queueMicrotask(() => {
          void drainFollowUpQueue(id);
        });
      } else if (!waitingForApproval(id) && useAgentMessageQueue.getState().items[id]?.length) {
        useAgentMessageQueue.setState((queue) => ({ paused: { ...queue.paused, [id]: true } }));
      }
    }
  }
});

useAgentApprovalStore.subscribe((state, previous) => {
  for (const [id, entry] of Object.entries(state.entries)) {
    if (
      previous.entries[id]?.items.some((row) => row.actionable) &&
      !entry.items.some((row) => row.actionable) &&
      !useAgentStore.getState().sending[id] &&
      useAgentStore.getState().details[id]?.messages.at(-1)?.status === "complete"
    ) {
      queueMicrotask(() => {
        void drainFollowUpQueue(id);
      });
    }
  }
});
