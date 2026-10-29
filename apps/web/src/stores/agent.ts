import { setConversationProject } from "@/apis/agent-projects";
import { undoAgentFile } from "@/apis/agent-files";
import { loadApprovals, markApprovalDecided } from "@/stores/agent-approvals";
import {
  streamAgentChat,
  generateAgentTitle,
  getAgentConfig,
  stopAgentRun,
  type SteeringEvent,
} from "@/apis/agents";
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
  pending: { id: string; signature: string; images?: import("@/types/agent").ChatImage[] } | null;
};
type State = {
  owner: number | null;
  agents: AgentConfig[];
  partnerCodes: AgentId[];
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
  partnerCodes: [],
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

/** 服务端冲突检查成功后，更新当前消息及历史分支中的撤销状态。 */
export async function undoFileChange(threadId: string, changeId: string) {
  const owner = currentOwner();
  const state = useAgentStore.getState();
  const detail = state.details[threadId];
  const code = state.agents.find((agent) => agent.id === detail?.thread.agent_id)?.code;
  if (!code || !detail) throw new Error("会话不存在。");
  await flushDraft(code, threadId);
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
    writeMock(`agent-config:${state.owner}`, {
      agents: state.agents,
      partner_codes: state.partnerCodes,
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
const runIds = new Map<string, string>();
const stops = new Map<string, Promise<void>>();
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
  runIds.clear();
  stops.clear();
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
      const legacy = readMock<State & { partner_codes?: AgentId[] }>(`agents:${owner}`);
      const saved =
        readMock<Pick<State, "agents" | "skills" | "selected"> & { partner_codes?: AgentId[] }>(
          `agent-config:${owner}`,
        ) ?? legacy;
      // 内置目录只提供模板；部门伙伴需要当前用户主动添加。
      const seen = new Set<string>();
      const skills: Skill[] = [];
      for (const meta of AGENTS)
        for (const name of meta.skills)
          if (!seen.has(name)) {
            seen.add(name);
            skills.push({ id: name, name, department: meta.department, description: name });
          }
      const agents: AgentConfig[] = AGENTS.map((meta) => ({
        id: meta.numericId,
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
        agents: agents.map((agent) => {
          const previous = saved?.agents?.find((row) => row.code === agent.code);
          return previous ? { ...agent, ...previous, id: agent.id, owner_id: owner } : agent;
        }),
        partnerCodes: (saved?.partner_codes ?? []).filter(
          (code) => code !== "general" && AGENTS.some((agent) => agent.id === code),
        ),
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
        // 保留升级前已有部门会话的可用性，空白的旧默认配置不算添加。
        partnerCodes: [
          ...new Set([
            ...state.partnerCodes,
            ...AGENTS.filter(
              (meta) =>
                saved?.partner_codes === undefined &&
                meta.id !== "general" &&
                rows.some((row) => row.agent_id === meta.numericId),
            ).map((meta) => meta.id),
          ]),
        ],
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
/** 每个账号默认仅通用 Agent；伙伴添加不创建会话或调用模型。 */
export function isAgentAdded(code: AgentId): boolean {
  return code === "general" || useAgentStore.getState().partnerCodes.includes(code);
}

export async function addPartner(code: AgentId) {
  const owner = useAuthStore.getState().user?.id;
  if (!owner) throw new Error("请登录后添加伙伴。");
  await loadAgents();
  if (!owned(owner)) throw new Error("登录状态已改变。");
  const agent = useAgentStore.getState().agents.find((row) => row.code === code);
  if (!agent) throw new Error("伙伴不存在。");
  // Sidecar 同时初始化工作目录和 AGENT.md；读取已有配置不会覆盖用户提示词。
  await getAgentConfig(code);
  if (!owned(owner)) throw new Error("登录状态已改变。");
  if (isAgentAdded(code)) return;
  const state = useAgentStore.getState();
  const partnerCodes = [...new Set([...state.partnerCodes, code])];
  writeMock(`agent-config:${owner}`, {
    agents: state.agents,
    skills: state.skills,
    selected: state.selected,
    partner_codes: partnerCodes,
  });
  useAgentStore.setState({ partnerCodes, agents: [...state.agents] });
}

/** 取消部门伙伴，保留其配置、工作空间和历史会话。 */
export async function removePartner(code: AgentId) {
  const owner = useAuthStore.getState().user?.id;
  if (!owner) throw new Error("请登录后管理伙伴。");
  await loadAgents();
  if (!owned(owner)) throw new Error("登录状态已改变。");
  if (code === "general") throw new Error("通用 Agent 是默认伙伴，不能取消。");
  const state = useAgentStore.getState();
  if (!state.partnerCodes.includes(code)) return;
  const partnerCodes = state.partnerCodes.filter((item) => item !== code);
  writeMock(`agent-config:${owner}`, {
    agents: state.agents,
    skills: state.skills,
    selected: state.selected,
    partner_codes: partnerCodes,
  });
  useAgentStore.setState({ partnerCodes, agents: [...state.agents] });
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
  const previous = state.lists[code]?.find((row) => row.id === thread.id);
  thread = { ...thread, has_history: thread.has_history ?? previous?.has_history ?? false };
  return {
    ...state.lists,
    [code]: [thread, ...(state.lists[code] ?? []).filter((row) => row.id !== thread.id)].sort(
      (a, b) => b.updated_at.localeCompare(a.updated_at),
    ),
  };
}
function remember(owner: number, code: AgentId, detail: ThreadDetail) {
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
  if (!isAgentAdded(code)) throw new Error("请先在伙伴中添加这个 Agent。");
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
function changeDraft(id: string, change: (draft: DraftState) => DraftState) {
  const owner = currentOwner();
  let code: AgentId | undefined;
  useAgentStore.setState((state) => {
    const draft = state.drafts[id];
    const thread = state.details[id]?.thread;
    code = state.agents.find((agent) => agent.id === thread?.agent_id)?.code;
    if (!draft) return state;
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
export function flushDraft(code: AgentId, id: string, duringSend = false): Promise<void> {
  const owner = currentOwner();
  const key = `${owner}:${id}`;
  const running = saves.get(key);
  if (running) return running;
  const operation = (async () => {
    for (let attempt = 0; attempt < 30; attempt++) {
      const state = useAgentStore.getState();
      const draft = state.drafts[id];
      const detail = state.details[id];
      if (
        !owned(owner) ||
        !draft ||
        !detail ||
        draft.version === draft.savedVersion ||
        detail.messages.some((row) => row.status === "waiting_approval") ||
        (draft.sending && !duringSend)
      )
        return;
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
              [id]: {
                ...state.details[id],
                thread: { ...state.details[id].thread, ...thread },
                knowledge_base_ids: draft.ids,
              },
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
  if (!runs.has(id)) return;
  if (!stops.has(id)) {
    const responseId = useAgentStore.getState().details[id]?.messages.at(-1)?.id;
    const stopping = stopAgentRun(id, responseId, runIds.get(id));
    stops.set(id, stopping);
    void stopping.catch(() => {});
  }
  runs.get(id)?.abort();
}

/** 修改历史提问，从该条消息重新生成后续回答。 */
export async function editMessage(
  code: AgentId,
  id: string,
  messageId: string,
  text: string,
  images?: import("@/types/agent").ChatImage[],
) {
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
  await sendMessage(code, id, text, {
    editedMessageId: messageId,
    images: images ?? detail.messages[index].context.images,
  });
}

/** 针对原用户消息生成新的助手分支，保留旧回复和输入草稿。 */
export async function regenerateMessage(code: AgentId, id: string, parentId: string | null) {
  currentOwner();
  const detail = useAgentStore.getState().details[id];
  const parent = detail?.messages.find((row) => row.id === parentId && row.role === "user");
  if (!parent) throw new Error("原消息不存在，请重新加载会话。");
  if (detail?.messages.at(-1)?.status === "waiting_approval")
    throw new Error("请先处理或停止当前审批。");
  await sendMessage(code, id, parent.content, {
    regenerateParentId: parent.id,
    images: parent.context.images,
    preserveDraft: true,
  });
}

export async function sendMessage(
  code: AgentId,
  id: string,
  text: string,
  options?: {
    editedMessageId?: string;
    regenerateParentId?: string;
    preserveDraft?: boolean;
    images?: import("@/types/agent").ChatImage[];
  },
) {
  const owner = currentOwner();
  if (!text.trim()) throw new Error("请输入消息。");
  const initial = useAgentStore.getState().drafts[id];
  if (!initial) throw new Error("会话尚未加载。");
  if (initial.sending) throw new Error("Agent 正在回复。");
  const agent = useAgentStore.getState().agents.find((row) => row.code === code);
  if (!agent || useAgentStore.getState().details[id]?.thread.agent_id !== agent.id)
    throw new Error("会话与 Agent 不匹配。");
  if (!options?.preserveDraft && initial.text !== text) setDraftText(id, text);
  const submittedVersion = useAgentStore.getState().drafts[id].version;
  const controller = new AbortController();
  runs.set(id, controller);
  useAgentStore.setState((state) => ({
    drafts: { ...state.drafts, [id]: { ...state.drafts[id], sending: true, error: null } },
  }));
  let replyId = "";
  try {
    await flushDraft(code, id, true);
    await mutations.get(`${owner}:${id}`);
    const state = useAgentStore.getState();
    if (!owned(owner) || !state.details[id]) return;
    const draft = state.drafts[id];
    const signature = JSON.stringify([
      text,
      [...draft.ids].sort(),
      options?.images?.map((image) => image.id) ?? [],
    ]);
    const pending =
      !options?.regenerateParentId && draft.pending?.signature === signature
        ? draft.pending
        : {
            id: crypto.randomUUID(),
            signature,
            ...(options?.images?.length ? { images: options.images } : {}),
          };
    replyId = `${pending.id}-reply`;
    const cut = options?.regenerateParentId
      ? state.details[id].messages.findIndex((row) => row.id === options.regenerateParentId) + 1
      : options?.editedMessageId
        ? state.details[id].messages.findIndex((row) => row.id === options.editedMessageId)
        : state.details[id].messages.length;
    if (cut < 0) throw new Error("待编辑消息已变化，请重新加载。");
    const history = state.details[id].messages
      .slice(0, cut)
      .filter((row) => row.id !== pending.id && row.id !== replyId);
    const now = new Date().toISOString();
    const context: ChatMessage["context"] = {
      ...(options?.images?.length ? { images: options.images } : {}),
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
      ...(options?.editedMessageId || options?.regenerateParentId
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
        ...(!options?.regenerateParentId
          ? [
              {
                id: pending.id,
                seq: history.length + 1,
                role: "user" as const,
                content: text,
                created_at: now,
                context,
                status: "complete" as const,
              },
            ]
          : []),
        {
          id: replyId,
          seq: history.length + (options?.regenerateParentId ? 1 : 2),
          role: "assistant",
          content: "",
          created_at: now,
          context: { ...context, images: [] },
          status: "streaming",
        },
      ],
    };
    useAgentStore.setState((current) => ({
      lists: updateList(current, code, detail.thread),
      details: { ...current.details, [id]: detail },
      drafts: {
        ...current.drafts,
        [id]: {
          ...current.drafts[id],
          pending,
          version: current.drafts[id].version + 1,
          ...(!options?.preserveDraft && current.drafts[id].version === submittedVersion
            ? {
                text: "",
              }
            : {}),
        },
      },
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
          ...(!options?.regenerateParentId ? [{ role: "user" as const, content: text }] : []),
        ],
      },
      (delta) => {
        accumulated += delta;
        updateReply(accumulated, "streaming");
      },
      controller.signal,
      (runId) => {
        if (owned(owner)) runIds.set(id, runId);
      },
      (event) => {
        if (!owned(owner)) return;
        applySteeringEvent(id, event);
        replyId = event.response_id;
        accumulated = "";
      },
      (trace) => {
        if (owned(owner)) applyToolTrace(id, replyId, trace);
      },
      (change) => {
        if (owned(owner)) applyFileChange(id, replyId, change);
      },
      (event) => {
        if (owned(owner)) applyReasoning(id, replyId, event);
      },
      (usage) => {
        if (owned(owner)) applyUsage(id, replyId, usage);
      },
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
          pending: null,
        },
      },
    }));
  } catch (error) {
    if (!owned(owner) || !useAgentStore.getState().details[id]) return;
    const cancelled = controller.signal.aborted;
    if (cancelled) await stops.get(id)?.catch(() => {});
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
          error: cancelled ? null : message(error),
          ...(cancelled ? { pending: null } : {}),
          ...(!cancelled && !options?.preserveDraft && !state.drafts[id].text
            ? { text, version: state.drafts[id].version + 1 }
            : {}),
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
    runIds.delete(id);
    stops.delete(id);
    if (owned(owner) && useAgentStore.getState().drafts[id]) {
      const current = useAgentStore.getState();
      const waiting = current.details[id]?.messages.some(
        (row) => row.status === "waiting_approval",
      );
      if (!waiting && !current.drafts[id].error) await flushDraft(code, id, true).catch(() => {});
      if (owned(owner))
        useAgentStore.setState((state) => ({
          drafts: {
            ...state.drafts,
            [id]: { ...state.drafts[id], sending: false },
          },
        }));
    }
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
        details: {
          ...next.details,
          [id]: { ...next.details[id], thread: { ...next.details[id].thread, ...thread } },
        },
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

/** 引导沿原 SSE 生效，接上用户补充指令及下一轮回复，不创建新运行。 */
function applyUsage(id: string, responseId: string, usage: import("@/types/agent").RunUsage) {
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

function applyFileChange(
  id: string,
  responseId: string,
  change: import("@/types/agent").FileChange,
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

function applyReasoning(
  id: string,
  responseId: string,
  event: import("@/apis/agents").ReasoningEvent,
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

function applyToolTrace(
  id: string,
  responseId: string,
  trace: import("@/types/agent").ToolExecution,
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

function applySteeringEvent(id: string, event: SteeringEvent) {
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
  let responseId = approval.response_id;
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
                row.id === responseId ? { ...row, content: accumulated, status: "streaming" } : row,
              ),
            },
          },
        }));
      },
      controller.signal,
      (runId) => {
        if (!owned(owner)) return;
        runIds.set(id, runId);
        markApprovalDecided(approval, decision);
        useAgentStore.setState((state) => ({
          details: {
            ...state.details,
            [id]: {
              ...state.details[id],
              messages: state.details[id].messages.map((row) =>
                row.id === responseId ? { ...row, status: "streaming" } : row,
              ),
            },
          },
        }));
      },
      (event) => {
        if (!owned(owner)) return;
        applySteeringEvent(id, event);
        responseId = event.response_id;
        accumulated = "";
      },
      (trace) => {
        if (owned(owner)) applyToolTrace(id, responseId, trace);
      },
      (change) => {
        if (owned(owner)) applyFileChange(id, responseId, change);
      },
      (event) => {
        if (owned(owner)) applyReasoning(id, responseId, event);
      },
      (usage) => {
        if (owned(owner)) applyUsage(id, responseId, usage);
      },
    );
  } finally {
    if (controller.signal.aborted) await stops.get(id)?.catch(() => {});
    if (runs.get(id) === controller) runs.delete(id);
    runIds.delete(id);
    stops.delete(id);
    if (owned(owner)) {
      try {
        remember(owner, code, await getConversation(id));
      } finally {
        if (owned(owner)) {
          await flushDraft(code, id, true).catch(() => {});
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
