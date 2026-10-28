import { setConversationProject } from "@/apis/agent-projects";
import { loadApprovals } from "@/stores/agent-approvals";
import { streamAgentChat, generateAgentTitle } from "@/apis/agents";
import {
  listConversations,
  getConversation,
  createConversation,
  saveConversationDraft,
  saveConversationMessages,
  renameConversation,
  deleteConversation,
  importConversation,
} from "@/apis/conversations";
import { useAppStore } from "@/stores/app";
import { useAgentModelStore } from "@/stores/agent-models";
import { readMock, writeMock } from "@/lib/mock-storage";
import { create } from "zustand";
import { useAuthStore } from "@/stores/auth";
import type { AgentId } from "@/interfaces/app";
import type {
  AgentConfig,
  ChatThread,
  Skill,
  ThreadDetail,
  ChatMessage,
  MessageBranch,
} from "@/types/agent";
import { AGENTS } from "@/features/agent/constants/agents";
export type DraftState = {
  text: string;
  ids: (string | number)[];
  version: number;
  savedVersion: number;
  error: string | null;
  saving: boolean;
  sending: boolean;
  pending: { id: string; signature: string } | null;
};
type State = {
  owner: number | null;
  agents: AgentConfig[];
  skills: Skill[];
  loading: boolean;
  error: string | null;
  lists: Partial<Record<AgentId, ChatThread[]>>;
  selected: Partial<Record<AgentId, string | null>>;
  details: Record<string, ThreadDetail>;
  drafts: Record<string, DraftState>;
  configBusy: boolean;
  switching: boolean;
};
const empty = (): State => ({
  owner: null,
  agents: [],
  skills: [],
  loading: false,
  error: null,
  lists: {},
  selected: {},
  details: {},
  drafts: {},
  configBusy: false,
  switching: false,
});
export const useAgentStore = create<State>(() => empty());
useAgentStore.subscribe((state, previous) => {
  if (
    !state.owner ||
    !state.agents.length ||
    (state.agents === previous.agents && state.selected === previous.selected)
  )
    return;
  // 本地仅保存 Agent 配置和当前选择，会话正文以 API / PG 为准。
  try {
    writeMock(`agent-config:${state.owner}`, {
      agents: state.agents,
      skills: state.skills,
      selected: state.selected,
    });
  } catch {
    /* 配置缓存不可用时不影响服务端会话。 */
  }
});
let bootstrap: Promise<void> | null = null;
let generation = 0;
const runs = new Map<string, AbortController>();
const titleRequests = new Map<string, Promise<string | undefined>>();
const timers = new Map<string, ReturnType<typeof setTimeout>>();
const saves = new Map<string, Promise<void>>();
const creates = new Map<string, Promise<string>>();
const createIds = new Map<string, string>();
const message = (error: unknown) => (error instanceof Error ? error.message : "操作失败，请重试。");
const mutations = new Map<string, Promise<unknown>>();
const removed = new Set<string>();
/** 串行提交同一会话的草稿和消息，避免自身请求产生版本冲突。 */
function mutate<T>(owner: number, id: string, operation: () => Promise<T>): Promise<T> {
  const key = `${owner}:${id}`;
  const version = generation;
  const previous = mutations.get(key) ?? Promise.resolve();
  const next = previous
    .catch(() => {})
    .then(() => {
      if (!owned(owner) || version !== generation || removed.has(key))
        throw new Error("会话已关闭或登录状态已改变。");
      return operation();
    });
  mutations.set(key, next);
  void next
    .finally(() => {
      if (mutations.get(key) === next) mutations.delete(key);
    })
    .catch(() => {});
  return next;
}
async function persistGraph(code: AgentId, id: string) {
  const owner = currentOwner();
  const snapshot = useAgentStore.getState().details[id];
  if (!snapshot) throw new Error("会话不存在。");
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

export function currentOwner() {
  const owner = useAuthStore.getState().user?.id;
  if (!owner || useAgentStore.getState().owner !== owner)
    throw new Error("登录状态已改变，请重试。");
  return owner;
}
export function resetAgents() {
  generation++;
  bootstrap = null;
  for (const controller of runs.values()) controller.abort();
  runs.clear();
  titleRequests.clear();
  mutations.clear();
  removed.clear();
  creates.clear();
  createIds.clear();
  saves.clear();
  for (const timer of timers.values()) clearTimeout(timer);
  timers.clear();
  useAgentStore.setState(empty());
}
function owned(owner: number) {
  return useAuthStore.getState().user?.id === owner && useAgentStore.getState().owner === owner;
}
export function loadAgents(force = false) {
  const owner = useAuthStore.getState().user?.id;
  if (!owner) return Promise.resolve();
  const old = useAgentStore.getState();
  if (old.owner !== owner) {
    resetAgents();
    useAgentStore.setState({ owner });
  }
  if (bootstrap) return bootstrap;
  if (!force && useAgentStore.getState().agents.length && !useAgentStore.getState().error)
    return Promise.resolve();
  const version = generation;
  useAgentStore.setState({ loading: true, error: null });
  const operation = (async () => {
    try {
      const legacy = readMock<State>(`agents:${owner}`);
      const saved =
        readMock<Pick<State, "agents" | "skills" | "selected">>(`agent-config:${owner}`) ?? legacy;
      // Agent 配置暂使用本地常量，执行模型由服务端环境配置。
      const seen = new Set<string>();
      const skills: Skill[] = [];
      for (const meta of AGENTS)
        for (const name of meta.skills)
          if (!seen.has(name)) {
            seen.add(name);
            skills.push({ id: name, name, department: meta.department, description: name });
          }
      const agents: AgentConfig[] = AGENTS.map((meta, index) => ({
        id: index + 1,
        owner_id: owner,
        code: meta.id,
        name: meta.name,
        department: meta.department,
        description: meta.description,
        knowledge_base_ids: [],
        skill_ids: meta.skills,
        revision: 1,
        active_thread_id: null,
      }));
      if (!owned(owner) || version !== generation) return;
      useAgentStore.setState({
        agents: saved?.agents?.length ? saved.agents : agents,
        skills: saved?.skills?.length ? saved.skills : skills,
        selected: saved?.selected ?? {},
      });
      if (legacy?.owner === owner) {
        for (const entry of Object.values(legacy.details ?? {})) {
          if (!owned(owner) || version !== generation) return;
          const draft = legacy.drafts?.[entry.thread.id];
          await importConversation({
            ...entry,
            thread: {
              ...entry.thread,
              draft: draft?.text ?? entry.thread.draft,
              title_source:
                entry.thread.title_source ??
                (entry.thread.title === "新会话" ? "pending" : "manual"),
            },
            knowledge_base_ids: draft?.ids ?? entry.knowledge_base_ids,
          });
        }
        if (!owned(owner) || version !== generation) return;
        localStorage.removeItem?.(`dp-work:mock:v1:agents:${owner}`);
      }
      const rows = await listConversations();
      if (!owned(owner) || version !== generation) return;
      useAgentStore.setState((state) => ({
        loading: false,
        lists: Object.fromEntries(
          state.agents.map((agent) => [
            agent.code,
            rows.filter((row) => row.agent_id === agent.id),
          ]),
        ),
      }));
    } catch (error) {
      if (owned(owner) && version === generation)
        useAgentStore.setState({ loading: false, error: message(error) });
      throw error;
    }
  })();
  bootstrap = operation;
  void operation
    .finally(() => {
      if (bootstrap === operation) bootstrap = null;
    })
    .catch(() => {});
  return operation;
}
export async function saveAgent(
  code: AgentId,
  changes: Pick<
    AgentConfig,
    "name" | "department" | "description" | "knowledge_base_ids" | "skill_ids"
  >,
) {
  const owner = currentOwner();
  const state = useAgentStore.getState();
  if (state.configBusy) throw new Error("配置正在保存，请稍后重试。");
  const agent = state.agents.find((row) => row.code === code);
  if (!agent) throw new Error("Agent 尚未加载。");
  useAgentStore.setState({ configBusy: true });
  try {
    // 配置暂保存为本地快照，不写入数据库。
    const updated: AgentConfig = {
      ...agent,
      ...changes,
      revision: agent.revision + 1,
    };
    if (owned(owner))
      useAgentStore.setState((state) => ({
        agents: state.agents.map((row) => (row.code === code ? updated : row)),
      }));
    return updated;
  } finally {
    if (owned(owner)) useAgentStore.setState({ configBusy: false });
  }
}
function updateList(state: State, code: AgentId, thread: ChatThread) {
  return {
    ...state.lists,
    [code]: [thread, ...(state.lists[code] ?? []).filter((row) => row.id !== thread.id)].sort(
      (a, b) => b.updated_at.localeCompare(a.updated_at),
    ),
  };
}
function remember(owner: number, code: AgentId, detail: ThreadDetail) {
  if (!owned(owner) || removed.has(`${owner}:${detail.thread.id}`)) return;
  useAgentStore.setState((state) => {
    const existing = state.drafts[detail.thread.id];
    const previous = state.details[detail.thread.id];
    if (previous && previous.thread.draft_revision > detail.thread.draft_revision) return state;
    return {
      lists: updateList(state, code, detail.thread),
      details: { ...state.details, [detail.thread.id]: detail },
      drafts: {
        ...state.drafts,
        [detail.thread.id]:
          existing && existing.version > existing.savedVersion
            ? existing
            : {
                text: detail.thread.draft,
                ids: detail.knowledge_base_ids,
                version: 0,
                savedVersion: 0,
                error: null,
                saving: false,
                sending: existing?.sending ?? false,
                pending: existing?.pending ?? null,
              },
      },
    };
  });
}
export async function loadThreads(code: AgentId) {
  currentOwner();
  return useAgentStore.getState().lists[code] ?? [];
}
export function createThread(code: AgentId, projectId: string | null = null): Promise<string> {
  const owner = currentOwner();
  const key = `${owner}:${code}:${projectId ?? ""}`;
  const running = creates.get(key);
  if (running) return running;
  const operation = (async () => {
    const selected = useAgentStore.getState().selected[code];
    if (selected) await flushDraft(code, selected);
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
    const old = useAgentStore.getState().selected[code];
    if (old && old !== id) await flushDraft(code, old);
    const detail = await getConversation(id);
    const agent = useAgentStore.getState().agents.find((row) => row.code === code);
    if (!detail || detail.thread.agent_id !== agent?.id) throw new Error("会话不存在。");
    remember(owner, code, detail);
    if (owned(owner))
      useAgentStore.setState((state) => ({ selected: { ...state.selected, [code]: id } }));
  } finally {
    if (owned(owner)) useAgentStore.setState({ switching: false });
  }
}
export async function ensureAgentChat(code: AgentId, force = false) {
  const owner = useAuthStore.getState().user?.id;
  if (!owner) return;
  await loadAgents(force);
  // 初始化过程中退出或切换账号时，丢弃旧账号的恢复任务。
  if (!owned(owner)) return;
  const rows = await loadThreads(code);
  if (!owned(owner)) return;
  const state = useAgentStore.getState();
  let id = state.selected[code];
  if (!id || !rows.some((row) => row.id === id)) id = rows[0]?.id;
  if (!id) {
    await createThread(code);
    return;
  }
  if (!state.details[id] || state.selected[code] !== id) await selectThread(code, id);
}
function changeDraft(id: string, change: (draft: DraftState) => DraftState) {
  const owner = currentOwner();
  let code: AgentId | undefined;
  useAgentStore.setState((state) => {
    const draft = state.drafts[id];
    const thread = state.details[id]?.thread;
    code = state.agents.find((agent) => agent.id === thread?.agent_id)?.code;
    if (!draft || draft.sending) return state;
    const next = change(draft);
    return {
      drafts: {
        ...state.drafts,
        [id]: { ...next, version: draft.version + 1, error: null, pending: null },
      },
    };
  });
  if (!code) return;
  const timerKey = `${owner}:${id}`;
  const previous = timers.get(timerKey);
  if (previous) clearTimeout(previous);
  timers.set(
    timerKey,
    setTimeout(() => {
      timers.delete(timerKey);
      if (owned(owner)) void flushDraft(code!, id).catch(() => {});
    }, 600),
  );
}
export const setDraftText = (id: string, text: string) =>
  changeDraft(id, (draft) => ({ ...draft, text }));
export const setDraftKnowledge = (id: string, ids: (string | number)[]) =>
  changeDraft(id, (draft) => ({ ...draft, ids: [...new Set(ids)] }));
export function flushDraft(code: AgentId, id: string): Promise<void> {
  const owner = currentOwner();
  const key = `${owner}:${id}`;
  const running = saves.get(key);
  if (running) return running;
  const operation = (async () => {
    for (let attempt = 0; attempt < 30; attempt++) {
      const state = useAgentStore.getState();
      const draft = state.drafts[id];
      const detail = state.details[id];
      if (!owned(owner) || !draft || !detail || draft.version === draft.savedVersion) return;
      useAgentStore.setState((state) => ({
        drafts: { ...state.drafts, [id]: { ...state.drafts[id], saving: true } },
      }));
      try {
        await mutate(owner, id, async () => {
          const current = useAgentStore.getState().details[id];
          const thread = await saveConversationDraft(id, {
            expected_revision: current.thread.draft_revision,
            draft: draft.text,
            knowledge_base_ids: draft.ids,
          });
          if (!owned(owner) || removed.has(`${owner}:${id}`)) return;
          useAgentStore.setState((state) => ({
            lists: updateList(state, code, thread),
            details: {
              ...state.details,
              [id]: { ...state.details[id], thread, knowledge_base_ids: draft.ids },
            },
            drafts: {
              ...state.drafts,
              [id]: {
                ...state.drafts[id],
                savedVersion: draft.version,
                saving: false,
                error: null,
              },
            },
          }));
        });
      } catch (error) {
        if (owned(owner))
          useAgentStore.setState((state) => ({
            drafts: {
              ...state.drafts,
              [id]: { ...state.drafts[id], saving: false, error: message(error) },
            },
          }));
        throw error;
      }
    }
    throw new Error("仍有未保存内容，请稍后重试。");
  })();
  saves.set(key, operation);
  void operation
    .finally(() => {
      if (saves.get(key) === operation) saves.delete(key);
    })
    .catch(() => {});
  return operation;
}
/** 停止当前会话的生成，并中断 API 和 Sidecar 的上游流。 */
export function cancelMessage(id: string) {
  runs.get(id)?.abort();
}

/** 修改历史提问，从该条消息重新生成后续回答。 */
export async function editMessage(code: AgentId, id: string, messageId: string, text: string) {
  currentOwner();
  const state = useAgentStore.getState();
  const detail = state.details[id];
  const agent = state.agents.find((row) => row.code === code);
  if (!detail || !state.drafts[id] || detail.thread.agent_id !== agent?.id)
    throw new Error("会话不存在或与 Agent 不匹配。");
  if (state.drafts[id].sending) throw new Error("请先停止当前生成，再编辑消息。");
  if (!text.trim()) throw new Error("请输入消息。");
  const index = detail.messages.findIndex((row) => row.id === messageId && row.role === "user");
  if (index < 0) throw new Error("只能编辑当前会话中的用户消息。");
  await sendMessage(code, id, text, { editedMessageId: messageId });
}

export async function sendMessage(
  code: AgentId,
  id: string,
  text: string,
  options?: { editedMessageId: string },
) {
  const owner = currentOwner();
  if (!text.trim()) throw new Error("请输入消息。");
  const initial = useAgentStore.getState().drafts[id];
  if (!initial) throw new Error("会话尚未加载。");
  if (initial.sending) throw new Error("Agent 正在回复。");
  const agent = useAgentStore.getState().agents.find((row) => row.code === code);
  if (!agent || useAgentStore.getState().details[id]?.thread.agent_id !== agent.id)
    throw new Error("会话与 Agent 不匹配。");
  if (initial.text !== text) setDraftText(id, text);
  const controller = new AbortController();
  runs.set(id, controller);
  useAgentStore.setState((state) => ({
    drafts: { ...state.drafts, [id]: { ...state.drafts[id], sending: true, error: null } },
  }));
  let replyId = "";
  try {
    await flushDraft(code, id);
    await mutations.get(`${owner}:${id}`);
    const state = useAgentStore.getState();
    if (!owned(owner) || !state.details[id]) return;
    const draft = state.drafts[id];
    const signature = JSON.stringify([text, [...draft.ids].sort()]);
    const pending =
      draft.pending?.signature === signature
        ? draft.pending
        : { id: crypto.randomUUID(), signature };
    replyId = `${pending.id}-reply`;
    const cut = options
      ? state.details[id].messages.findIndex((row) => row.id === options.editedMessageId)
      : state.details[id].messages.length;
    if (cut < 0) throw new Error("待编辑消息已变化，请重新加载。");
    const history = state.details[id].messages
      .slice(0, cut)
      .filter((row) => row.id !== pending.id && row.id !== replyId);
    const now = new Date().toISOString();
    const context: ChatMessage["context"] = {
      knowledge_bases: [],
      skills: [],
      agent: {
        id: agent.id,
        name: agent.name,
        department: agent.department,
        revision: agent.revision,
      },
    };
    const detail: ThreadDetail = {
      ...state.details[id],
      ...(options
        ? {
            message_branches: collectMessageBranches(
              state.details[id].messages,
              state.details[id].message_branches,
            ),
          }
        : {}),
      thread: {
        ...state.details[id].thread,
        updated_at: now,
      },
      messages: [
        ...history,
        {
          id: pending.id,
          seq: history.length + 1,
          role: "user",
          content: text,
          created_at: now,
          context,
          status: "complete",
        },
        {
          id: replyId,
          seq: history.length + 2,
          role: "assistant",
          content: "",
          created_at: now,
          context,
          status: "streaming",
        },
      ],
    };
    useAgentStore.setState((current) => ({
      lists: updateList(current, code, detail.thread),
      details: { ...current.details, [id]: detail },
      drafts: { ...current.drafts, [id]: { ...current.drafts[id], pending } },
    }));
    const updateReply = (content: string, status: ChatMessage["status"]) => {
      if (!owned(owner) || !useAgentStore.getState().details[id]) return;
      useAgentStore.setState((current) => ({
        details: {
          ...current.details,
          [id]: {
            ...current.details[id],
            messages: current.details[id].messages.map((row) =>
              row.id === replyId ? { ...row, content, status } : row,
            ),
          },
        },
      }));
    };
    await persistGraph(code, id);
    if (!owned(owner)) return;
    let accumulated = "";
    const selectedModel = useAppStore.getState().currentModel;
    const model = useAgentModelStore.getState().data?.models.some((row) => row.id === selectedModel)
      ? selectedModel
      : undefined;
    const content = await streamAgentChat(
      {
        agent_code: code,
        thread_id: id,
        response_id: replyId,
        expected_revision: useAgentStore.getState().details[id].thread.draft_revision,
        knowledge_base_ids: (
          state.agents.find((row) => row.code === code)?.knowledge_base_ids ?? []
        )
          .map((value) => Number(String(value).replace(/^server-/, "")))
          .filter((value) => Number.isSafeInteger(value) && value > 0),
        model,
        messages: [
          ...history
            .filter(
              (row) =>
                row.content &&
                (row.role === "user" ||
                  row.status === "complete" ||
                  (!row.status && !row.content.includes("这是用于体验聊天流程的模拟回复"))),
            )
            .map((row) => ({ role: row.role, content: row.content })),
          { role: "user", content: text },
        ],
      },
      (delta) => {
        accumulated += delta;
        updateReply(accumulated, "streaming");
      },
      controller.signal,
    );
    if (content !== null) updateReply(content, "complete");
    if (content === null) void loadApprovals(id, true);
    const saved = await getConversation(id);
    if (!owned(owner) || !useAgentStore.getState().details[id]) return;
    remember(owner, code, saved);
    useAgentStore.setState((current) => ({
      drafts: {
        ...current.drafts,
        [id]: {
          ...current.drafts[id],
          text: saved.thread.draft,
          sending: false,
          pending: null,
          version: 0,
          savedVersion: 0,
        },
      },
    }));
  } catch (error) {
    if (!owned(owner) || !useAgentStore.getState().details[id]) return;
    const cancelled = controller.signal.aborted;
    useAgentStore.setState((state) => ({
      details: {
        ...state.details,
        [id]: {
          ...state.details[id],
          messages: state.details[id].messages.map((row) =>
            row.id === replyId
              ? {
                  ...row,
                  status: cancelled ? "cancelled" : "failed",
                  content: row.content || (cancelled ? "已停止生成。" : "生成失败，请重试。"),
                }
              : row,
          ),
        },
      },
      drafts: {
        ...state.drafts,
        [id]: {
          ...state.drafts[id],
          sending: false,
          error: cancelled ? null : message(error),
          ...(cancelled ? { text: "", pending: null } : {}),
        },
      },
    }));
    try {
      const saved = await getConversation(id);
      const remote = saved.messages.find((row) => row.id === replyId);
      if (remote?.status === "streaming") {
        await persistGraph(code, id);
      } else remember(owner, code, saved);
    } catch {
      /* 保存失败保留页面错误和内容，可重新加载服务端版本。 */
    }
    if (owned(owner)) await loadApprovals(id, true);
    if (!cancelled) throw error;
  } finally {
    if (runs.get(id) === controller) runs.delete(id);
  }
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
    const drafts = { ...state.drafts };
    delete details[id];
    delete drafts[id];
    return {
      lists: { ...state.lists, [code]: (state.lists[code] ?? []).filter((row) => row.id !== id) },
      details,
      drafts,
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
  const version = generation;
  const firstId = detail.messages.find((row) => row.role === "user")?.id;
  if (!firstId) return Promise.resolve(undefined);
  let remaining = 16000;
  const messages = detail.messages
    .filter((row) => row.content.trim() && row.status !== "failed" && row.status !== "cancelled")
    .slice(0, 6)
    .map((row) => {
      const content = row.content.slice(0, Math.min(4000, remaining));
      remaining -= content.length;
      return { role: row.role, content };
    })
    .filter((row) => row.content.length > 0);
  const selectedModel = useAppStore.getState().currentModel;
  const model = useAgentModelStore.getState().data?.models.some((row) => row.id === selectedModel)
    ? selectedModel
    : undefined;
  const operation = (async () => {
    await mutations.get(`${owner}:${id}`);
    if (!owned(owner) || version !== generation) throw new Error("登录状态已改变。");
    return generateAgentTitle({ thread_id: id, messages, model });
  })()
    .then(async ({ title }) => {
      if (!owned(owner) || version !== generation) return undefined;
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
        details: { ...next.details, [id]: { ...next.details[id], thread } },
      }));
      return title;
    })
    .catch(() => undefined)
    .finally(() => {
      if (titleRequests.get(key) === operation) titleRequests.delete(key);
    });
  titleRequests.set(key, operation);
  return operation;
}

/** 保存运行时全部消息版本，可恢复旧页面里仍在内存中的分支。 */
export function preserveMessageBranches(id: string, branches: MessageBranch[]) {
  currentOwner();
  const detail = useAgentStore.getState().details[id];
  if (!detail || useAgentStore.getState().drafts[id]?.sending) return;
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
  if (!detail || !state.drafts[id] || state.drafts[id].sending) return;
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
    drafts: { ...current.drafts, [id]: { ...current.drafts[id], pending: null, error: null } },
  }));
  const code = getThreadAgentCode(id);
  if (code)
    void persistGraph(code, id).catch((error) => {
      if (!owned(state.owner!)) return;
      useAgentStore.setState((current) => ({
        drafts: { ...current.drafts, [id]: { ...current.drafts[id], error: message(error) } },
      }));
    });
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

/** 在原会话与原回复上恢复审批后的执行，不另建一条提问。 */
export async function resumeApprovedRun(
  approval: import("@/apis/agent-approvals").AgentApproval,
  decision: "approve" | "reject",
) {
  const owner = currentOwner();
  const id = approval.conversation_id;
  const code = getThreadAgentCode(id);
  if (!code || runs.has(id)) throw new Error("会话正在执行，请稍后重试。");
  if (!useAgentStore.getState().details[id]) await selectThreadById(id);
  const controller = new AbortController();
  runs.set(id, controller);
  useAgentStore.setState((state) => ({
    drafts: { ...state.drafts, [id]: { ...state.drafts[id], sending: true, error: null } },
  }));
  let accumulated =
    useAgentStore.getState().details[id].messages.find((row) => row.id === approval.response_id)
      ?.content ?? "";
  try {
    await streamAgentChat(
      {
        agent_code: code,
        thread_id: id,
        messages: [],
        approval_request: { id: approval.id, decision },
      },
      (delta) => {
        if (!owned(owner)) return;
        accumulated += delta;
        useAgentStore.setState((state) => ({
          details: {
            ...state.details,
            [id]: {
              ...state.details[id],
              messages: state.details[id].messages.map((row) =>
                row.id === approval.response_id
                  ? { ...row, content: accumulated, status: "streaming" }
                  : row,
              ),
            },
          },
        }));
      },
      controller.signal,
    );
  } finally {
    if (runs.get(id) === controller) runs.delete(id);
    if (owned(owner)) {
      try {
        remember(owner, code, await getConversation(id));
      } finally {
        if (owned(owner)) {
          useAgentStore.setState((state) => ({
            drafts: { ...state.drafts, [id]: { ...state.drafts[id], sending: false } },
          }));
          await loadApprovals(id, true);
        }
      }
    }
  }
}

/** 选择会话工作目录前排空草稿保存，保持版本一致。 */
export async function changeThreadProject(id: string, projectId: string | null) {
  const owner = currentOwner();
  const code = getThreadAgentCode(id);
  if (!code) throw new Error("会话不存在。");
  await flushDraft(code, id);
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
