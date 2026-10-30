import type { ChatMessage, MessageBranch, SteeringEvent } from "@/interfaces/agent";
import { setConversationProject } from "@/apis/agents";
import { undoAgentFile } from "@/apis/agents";
import { listConversations, getConversation } from "@/apis/conversations";

import {
  currentOwner,
  mutate,
  owned,
  persistGraph,
  remember,
  updateList,
  useAgentStore,
} from "./state";
import { getThreadAgentCode } from "@/stores/agent/agent-threads";

/** 服务端冲突检查成功后，更新当前消息及历史分支中的撤销状态。 */
export async function undoFileChange(threadId: string, changeId: string) {
  const owner = currentOwner();
  const state = useAgentStore.getState();
  const detail = state.details[threadId];
  const code = state.agents.find((agent) => agent.id === detail?.thread.agent_id)?.code;
  if (!code || !detail) throw new Error("会话不存在。");
  return mutate(owner, threadId, async () => {
    const { change, thread } = await undoAgentFile(threadId, changeId);
    if (!owned(owner)) return;
    const update = (message: ChatMessage): ChatMessage => ({
      ...message,
      context: {
        ...message.context,
        file_changes: message.context.file_changes?.map((item) =>
          item.id === changeId ? change : item,
        ),
      },
    });
    useAgentStore.setState((state) => {
      const current = state.details[threadId];
      if (!current) return state;
      return {
        lists: updateList(state, code, thread),
        details: {
          ...state.details,
          [threadId]: {
            ...current,
            thread,
            messages: current.messages.map(update),
            message_branches: current.message_branches?.map((entry) => ({
              ...entry,
              message: update(entry.message),
            })),
          },
        },
      };
    });
    return change;
  });
}

/** 保存运行时全部消息版本，可恢复旧页面里仍在内存中的分支。 */
export function preserveMessageBranches(id: string, branches: MessageBranch[]) {
  currentOwner();
  const detail = useAgentStore.getState().details[id];
  if (!detail || useAgentStore.getState().sending[id]) return;
  const merged = new Map((detail.message_branches ?? []).map((entry) => [entry.message.id, entry]));
  for (const entry of branches) merged.set(entry.message.id, entry);
  useAgentStore.setState((state) => ({
    details: {
      ...state.details,
      [id]: { ...state.details[id], message_branches: [...merged.values()] },
    },
  }));
}

/** 左右切换只改变当前路径；其他版本继续保存在 PG。 */
export function selectMessageBranch(id: string, ids: readonly string[], branches: MessageBranch[]) {
  currentOwner();
  const state = useAgentStore.getState();
  const detail = state.details[id];
  if (!detail || state.sending[id]) return;
  const all = new Map(
    collectMessageBranches(detail.messages, detail.message_branches).map((entry) => [
      entry.message.id,
      entry,
    ]),
  );
  for (const entry of branches) all.set(entry.message.id, entry);
  if (
    ids.length === detail.messages.length &&
    ids.every((messageId, index) => detail.messages[index].id === messageId)
  )
    return;
  const selected = ids.map((messageId, index) => {
    const entry = all.get(messageId);
    if (!entry || entry.parentId !== (ids[index - 1] ?? null))
      throw new Error("消息分支无效，请重新加载。");
    return { ...entry.message, seq: index + 1 };
  });
  useAgentStore.setState((current) => ({
    details: {
      ...current.details,
      [id]: { ...current.details[id], messages: selected, message_branches: [...all.values()] },
    },
  }));
  const code = getThreadAgentCode(id);
  if (code) void persistGraph(code, id).catch(() => {});
}

/** 合并所有历史节点与当前对话路径，按消息 ID 更新流式正文。 */
export function collectMessageBranches(
  messages: readonly ChatMessage[],
  saved: readonly MessageBranch[] = [],
): MessageBranch[] {
  const all = new Map(saved.map((entry) => [entry.message.id, entry]));
  messages.forEach((message, index) =>
    all.set(message.id, { parentId: messages[index - 1]?.id ?? null, message }),
  );
  return [...all.values()];
}

/** 引导沿原 SSE 生效，接上用户补充指令及下一轮回复，不创建新运行。 */
export function applyUsage(
  id: string,
  responseId: string,
  usage: import("@/interfaces/agent").RunUsage,
) {
  useAgentStore.setState((state) => {
    const detail = state.details[id];
    if (!detail) return state;
    return {
      details: {
        ...state.details,
        [id]: {
          ...detail,
          messages: detail.messages.map((row) =>
            row.id === responseId ? { ...row, context: { ...row.context, usage } } : row,
          ),
        },
      },
    };
  });
}

export function applyFileChange(
  id: string,
  responseId: string,
  change: import("@/interfaces/agent").FileChange,
) {
  useAgentStore.setState((state) => {
    const detail = state.details[id];
    if (!detail) return state;
    return {
      details: {
        ...state.details,
        [id]: {
          ...detail,
          messages: detail.messages.map((row) => {
            if (row.id !== responseId) return row;
            const changes = row.context.file_changes ?? [];
            return changes.some((item) => item.id === change.id)
              ? row
              : { ...row, context: { ...row.context, file_changes: [...changes, change] } };
          }),
        },
      },
    };
  });
}

export function applyReasoning(
  id: string,
  responseId: string,
  event: import("@/interfaces/agent").ReasoningEvent,
) {
  useAgentStore.setState((state) => {
    const detail = state.details[id];
    if (!detail) return state;
    return {
      details: {
        ...state.details,
        [id]: {
          ...detail,
          messages: detail.messages.map((row) => {
            if (row.id !== responseId) return row;
            const thoughts = row.context.reasoning ?? [];
            const previous = thoughts.find((item) => item.id === event.id);
            const next = {
              id: event.id,
              text: (previous?.text ?? "") + (event.text ?? ""),
              started_at: event.started_at,
              ...(event.completed_at ? { completed_at: event.completed_at } : {}),
            };
            const order =
              row.context.execution_order ??
              (row.context.tool_calls ?? []).map((call) => "tool:" + call.id);
            return {
              ...row,
              context: {
                ...row.context,
                reasoning: previous
                  ? thoughts.map((item) => (item.id === event.id ? next : item))
                  : [...thoughts, next],
                execution_order: order.includes("reasoning:" + event.id)
                  ? order
                  : [...order, "reasoning:" + event.id],
              },
            };
          }),
        },
      },
    };
  });
}

export function applyToolTrace(
  id: string,
  responseId: string,
  trace: import("@/interfaces/agent").ToolExecution,
) {
  useAgentStore.setState((state) => {
    const detail = state.details[id];
    if (!detail) return state;
    return {
      details: {
        ...state.details,
        [id]: {
          ...detail,
          messages: detail.messages.map((row) => {
            if (row.id !== responseId) return row;
            const calls = row.context.tool_calls ?? [];
            return {
              ...row,
              context: {
                ...row.context,
                execution_order: [
                  ...new Set([
                    ...(row.context.execution_order ?? calls.map((call) => "tool:" + call.id)),
                    "tool:" + trace.id,
                  ]),
                ],
                tool_calls: calls.some((call) => call.id === trace.id)
                  ? calls.map((call) => (call.id === trace.id ? trace : call))
                  : [...calls, trace],
              },
            };
          }),
        },
      },
    };
  });
}

export function applySteeringEvent(id: string, event: SteeringEvent) {
  useAgentStore.setState((state) => {
    const current = state.details[id];
    if (!current || current.messages.some((row) => row.id === event.id)) return state;
    const before = current.messages.flatMap((row) =>
      row.id !== event.previous_response_id
        ? [row]
        : event.previous_removed
          ? []
          : [{ ...row, content: event.previous_content, status: "complete" as const }],
    );
    const messages = [...before, event.message, event.response].map((row, index) => ({
      ...row,
      seq: index + 1,
    }));
    const branches = (current.message_branches ?? []).filter(
      (entry) => !event.previous_removed || entry.message.id !== event.previous_response_id,
    );
    return {
      details: {
        ...state.details,
        [id]: {
          ...current,
          thread: { ...current.thread, ...event.thread },
          messages,
          message_branches: collectMessageBranches(messages, branches),
        },
      },
    };
  });
}

/** 选择会话工作目录。 */
export async function changeThreadProject(id: string, projectId: string | null) {
  const owner = currentOwner();
  const code = getThreadAgentCode(id);
  if (!code) throw new Error("会话不存在。");
  await mutate(owner, id, async () => {
    const detail = useAgentStore.getState().details[id];
    const saved = await setConversationProject(id, projectId, detail.thread.draft_revision);
    if (owned(owner)) remember(owner, code, saved);
  });
}

/** 移除项目后刷新会话归属，保留所有消息与未保存草稿。 */
export async function refreshProjectConversations(projectId: string) {
  const owner = currentOwner();
  const affected = Object.values(useAgentStore.getState().details)
    .filter((detail) => detail.thread.project_id === projectId)
    .map((detail) => detail.thread.id);
  const rows = await listConversations();
  if (!owned(owner)) return;
  useAgentStore.setState((state) => ({
    lists: Object.fromEntries(
      state.agents.map((agent) => [agent.code, rows.filter((row) => row.agent_id === agent.id)]),
    ),
  }));
  await Promise.all(
    affected.map(async (id) => {
      const code = getThreadAgentCode(id);
      if (code) {
        const detail = await getConversation(id);
        if (owned(owner)) remember(owner, code, detail);
      }
    }),
  );
}
