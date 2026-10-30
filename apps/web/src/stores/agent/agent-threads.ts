import type { AgentId } from "@/interfaces/app";
import { generateAgentTitle } from "@/apis/agents";
import {
  getConversation,
  createConversation,
  renameConversation,
  deleteConversation,
} from "@/apis/conversations";
import { useAuthStore } from "@/stores/auth";
import { useAppStore } from "@/stores/app";
import { useAgentModelStore } from "@/stores/agent/agent-models";

import {
  createIds,
  creates,
  currentOwner,
  generationRef,
  mutations,
  owned,
  remember,
  removed,
  titleRequests,
  updateList,
  useAgentStore,
} from "./state";
import { isAgentAdded, loadAgents } from "@/stores/agent/agent-config";
import { cancelMessage } from "@/stores/agent/agent-send";

export async function loadThreads(code: AgentId) {
  currentOwner();
  return useAgentStore.getState().lists[code] ?? [];
}

export function createThread(code: AgentId, projectId: string | null = null): Promise<string> {
  if (!isAgentAdded(code)) throw new Error("请先在伙伴中添加这个 Agent。");
  const owner = currentOwner();
  const key = `${owner}:${code}:${projectId ?? ""}`;
  const running = creates.get(key);
  if (running) return running;
  const operation = (async () => {
    let id = createIds.get(key);
    if (!id) {
      id = crypto.randomUUID();
      createIds.set(key, id);
    }
    const agent = useAgentStore.getState().agents.find((row) => row.code === code);
    if (!agent) throw new Error("Agent 尚未加载。");
    const detail = await createConversation(id, agent.id, agent.knowledge_base_ids, projectId);
    createIds.delete(key);
    remember(owner, code, detail);
    if (owned(owner))
      useAgentStore.setState((state) => ({
        selected: { ...state.selected, [code]: detail.thread.id },
      }));
    return detail.thread.id;
  })();
  creates.set(key, operation);
  void operation
    .finally(() => {
      if (creates.get(key) === operation) creates.delete(key);
    })
    .catch(() => {});
  return operation;
}

/** 根据会话所属 Agent 查找业务标识。 */
export function getThreadAgentCode(id: string): AgentId | undefined {
  const state = useAgentStore.getState();
  if (state.owner !== useAuthStore.getState().user?.id) return undefined;
  const thread =
    state.details[id]?.thread ??
    Object.values(state.lists)
      .flat()
      .find((row) => row?.id === id);
  return state.agents.find((agent) => agent.id === thread?.agent_id)?.code;
}

/** 通过会话自身的 Agent 归属选中会话。 */
export async function selectThreadById(id: string): Promise<AgentId> {
  const code = getThreadAgentCode(id);
  if (!code) throw new Error("会话不存在或所属 Agent 不可用。");
  await selectThread(code, id);
  return code;
}

export async function selectThread(code: AgentId, id: string) {
  const owner = currentOwner();
  if (useAgentStore.getState().switching) return;
  useAgentStore.setState({ switching: true });
  try {
    const detail = await getConversation(id);
    const agent = useAgentStore.getState().agents.find((row) => row.code === code);
    if (!detail || detail.thread.agent_id !== agent?.id) throw new Error("会话不存在。");
    remember(owner, code, detail);
    if (owned(owner))
      useAgentStore.setState((state) => ({
        selected: { ...state.selected, [code]: id },
      }));
  } finally {
    if (owned(owner)) useAgentStore.setState({ switching: false });
  }
}

export async function ensureAgentChat(code: AgentId, force = false) {
  const owner = useAuthStore.getState().user?.id;
  if (!owner) return;
  await loadAgents(force);
  if (!isAgentAdded(code)) return;
  // 初始化过程中退出或切换账号时，丢弃旧账号的恢复任务。
  if (!owned(owner)) return;
  const rows = await loadThreads(code);
  if (!owned(owner)) return;
  const state = useAgentStore.getState();
  let id = state.selected[code];
  if (id && state.details[id]) return;
  if (id && !rows.some((row) => row.id === id)) {
    try {
      await selectThread(code, id);
      return;
    } catch {
      if (!owned(owner)) return;
    }
  }
  if (!id || !rows.some((row) => row.id === id)) id = rows[0]?.id;
  if (!id) {
    if (state.selected[code])
      useAgentStore.setState((current) => ({ selected: { ...current.selected, [code]: null } }));
    return;
  }
  if (!state.details[id] || state.selected[code] !== id) await selectThread(code, id);
}

export async function renameThread(code: AgentId, id: string, title: string) {
  const owner = currentOwner();
  const state = useAgentStore.getState();
  const existing = state.details[id]?.thread;
  const agent = state.agents.find((row) => row.code === code);
  if (!existing || existing.agent_id !== agent?.id) throw new Error("会话不存在。");
  const row = await renameConversation(id, title);
  if (owned(owner))
    useAgentStore.setState((state) => ({
      lists: updateList(state, code, row),
      details: state.details[id]
        ? {
            ...state.details,
            [id]: {
              ...state.details[id],
              thread: { ...state.details[id].thread, title: row.title, title_source: "manual" },
            },
          }
        : state.details,
    }));
}

export async function removeThread(code: AgentId, id: string) {
  const owner = currentOwner();
  cancelMessage(id);
  await deleteConversation(id);
  removed.add(`${owner}:${id}`);
  if (!owned(owner)) return;
  useAgentStore.setState((state) => {
    const details = { ...state.details };
    delete details[id];
    return {
      lists: { ...state.lists, [code]: (state.lists[code] ?? []).filter((row) => row.id !== id) },
      details,
      selected: state.selected[code] === id ? { ...state.selected, [code]: null } : state.selected,
    };
  });
}

/** 首轮对话后生成标题；去重请求，并防止覆盖重命名或新账号。 */
export function generateThreadTitle(id: string): Promise<string | undefined> {
  const owner = currentOwner();
  const state = useAgentStore.getState();
  const detail = state.details[id];
  if (!detail) return Promise.resolve(undefined);
  if (detail.thread.title_source !== "pending") return Promise.resolve(detail.thread.title);
  const key = `${owner}:${id}`;
  const running = titleRequests.get(key);
  if (running) return running;
  const version = generationRef.current;
  const firstId = detail.messages.find((row) => row.role === "user")?.id;
  if (!firstId) return Promise.resolve(undefined);
  if (
    !detail.messages.some(
      (row) => row.role === "assistant" && row.status === "complete" && row.content.trim(),
    )
  )
    return Promise.resolve(undefined);
  const first = detail.messages.find((row) => row.id === firstId)!;
  const messages = [{ role: "user" as const, content: first.content.slice(0, 4000) }];
  const selectedModel = useAppStore.getState().currentModel;
  const model = useAgentModelStore.getState().data?.models.some((row) => row.id === selectedModel)
    ? selectedModel
    : undefined;
  const operation: Promise<string | undefined> = (async () => {
    try {
      await mutations.get(`${owner}:${id}`);
      if (!owned(owner) || version !== generationRef.current) throw new Error("登录状态已改变。");
      const { title } = await generateAgentTitle({ thread_id: id, messages, model });
      if (!owned(owner) || version !== generationRef.current) return undefined;
      const current = useAgentStore.getState().details[id];
      if (!current) return undefined;
      if (current.thread.title_source !== "pending") return current.thread.title;
      if (current.messages.find((row) => row.role === "user")?.id !== firstId) return undefined;
      const code = getThreadAgentCode(id);
      if (!code) return undefined;
      const thread = await renameConversation(id, title, "generated", firstId);
      if (!owned(owner) || !useAgentStore.getState().details[id]) return undefined;
      useAgentStore.setState((next) => ({
        lists: updateList(next, code, thread),
        details: {
          ...next.details,
          [id]: { ...next.details[id], thread: { ...next.details[id].thread, ...thread } },
        },
      }));
      return title;
    } catch {
      return undefined;
    }
  })().finally(() => {
    if (titleRequests.get(key) === operation) titleRequests.delete(key);
  });
  titleRequests.set(key, operation);
  return operation;
}
