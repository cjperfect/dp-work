import { streamAgentChat } from "@/apis/agents";
import { useAppStore } from "@/stores/app";
import { useAgentModelStore } from "@/stores/agent-models";
import { readMock, writeMock } from "@/lib/mock-storage";
import { create } from "zustand";
import { useAuthStore } from "@/stores/auth";
import type { AgentId } from "@/interfaces/app";
import type { AgentConfig, ChatThread, Skill, ThreadDetail, ChatMessage } from "@/types/agent";
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
useAgentStore.subscribe((state) => {
  if (
    !state.owner ||
    !state.agents.length ||
    Object.values(state.drafts).some((draft) => draft.sending)
  )
    return;
  try {
    writeMock(`agents:${state.owner}`, {
      ...state,
      configBusy: false,
      switching: false,
      loading: false,
      error: null,
      drafts: Object.fromEntries(
        Object.entries(state.drafts).map(([id, draft]) => [
          id,
          { ...draft, sending: false, saving: false, pending: null },
        ]),
      ),
    });
  } catch {
    /* 演示存储不可用时保留当前页面数据。 */
  }
});
let bootstrap: Promise<void> | null = null;
let generation = 0;
const runs = new Map<string, AbortController>();
const timers = new Map<string, ReturnType<typeof setTimeout>>();
const saves = new Map<string, Promise<void>>();
const creates = new Map<string, Promise<string>>();
const createIds = new Map<string, string>();
const message = (error: unknown) => (error instanceof Error ? error.message : "操作失败，请重试。");
/** 构造本地会话，模型执行通过 Agent API 完成。 */
function localThread(id: string, agentId: number, title = "新会话"): ThreadDetail {
  const now = new Date().toISOString();
  return {
    thread: {
      id,
      agent_id: agentId,
      title,
      draft: "",
      draft_revision: 0,
      created_at: now,
      updated_at: now,
    },
    knowledge_base_ids: [],
    messages: [],
  };
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
  if (!force && useAgentStore.getState().agents.length) return Promise.resolve();
  const version = generation;
  useAgentStore.setState({ loading: true, error: null });
  const operation = (async () => {
    try {
      const saved = readMock<State>(`agents:${owner}`);
      if (saved?.owner === owner && saved.agents?.length) {
        if (owned(owner) && version === generation)
          useAgentStore.setState({
            ...saved,
            loading: false,
            error: null,
            configBusy: false,
            switching: false,
          });
        return;
      }
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
      const data: { agents: AgentConfig[]; skills: Skill[] } = { agents, skills };
      if (!owned(owner) || version !== generation) return;
      useAgentStore.setState((state) => ({
        agents: data.agents,
        skills: data.skills,
        loading: false,
        selected: Object.fromEntries(
          data.agents.map((agent) => [
            agent.code,
            state.selected[agent.code] === undefined
              ? agent.active_thread_id
              : state.selected[agent.code],
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
  if (!owned(owner)) return;
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
                sending: false,
                pending: null,
              },
      },
    };
  });
}
export async function loadThreads(code: AgentId) {
  currentOwner();
  // 本地会话列表是当前数据源，重新进入页面时保留已有会话。
  return useAgentStore.getState().lists[code] ?? [];
}
export function createThread(code: AgentId): Promise<string> {
  const owner = currentOwner();
  const key = `${owner}:${code}`;
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
    // 本阶段会话历史保存在本地。
    const agent = useAgentStore.getState().agents.find((row) => row.code === code);
    if (!agent) throw new Error("Agent 尚未加载。");
    const detail = localThread(id, agent.id);
    detail.knowledge_base_ids = [...agent.knowledge_base_ids];
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
    const detail = useAgentStore.getState().details[id];
    const agent = useAgentStore.getState().agents.find((row) => row.code === code);
    if (!detail || detail.thread.agent_id !== agent?.id) throw new Error("会话不存在。");
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
  if (owned(owner) && state.selected[code] !== id)
    useAgentStore.setState((state) => ({ selected: { ...state.selected, [code]: id } }));
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
        // 草稿保存在本地，不调用业务 API。
        if (!owned(owner)) return;
        useAgentStore.setState((state) => ({
          lists: updateList(state, code, detail.thread),
          drafts: {
            ...state.drafts,
            [id]: { ...state.drafts[id], savedVersion: draft.version, saving: false, error: null },
          },
        }));
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
  useAgentStore.setState((current) => ({
    details: { ...current.details, [id]: { ...detail, messages: detail.messages.slice(0, index) } },
    drafts: { ...current.drafts, [id]: { ...current.drafts[id], pending: null, error: null } },
  }));
  await sendMessage(code, id, text);
}

export async function sendMessage(code: AgentId, id: string, text: string) {
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
    const state = useAgentStore.getState();
    if (!owned(owner) || !state.details[id]) return;
    const draft = state.drafts[id];
    const signature = JSON.stringify([text, [...draft.ids].sort()]);
    const pending =
      draft.pending?.signature === signature
        ? draft.pending
        : { id: crypto.randomUUID(), signature };
    replyId = `${pending.id}-reply`;
    const history = state.details[id].messages.filter(
      (row) => row.id !== pending.id && row.id !== replyId,
    );
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
      thread: {
        ...state.details[id].thread,
        title:
          !history.length && state.details[id].thread.title === "新会话"
            ? text.slice(0, 24)
            : state.details[id].thread.title,
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
    let accumulated = "";
    const selectedModel = useAppStore.getState().currentModel;
    const model = useAgentModelStore.getState().data?.models.some((row) => row.id === selectedModel)
      ? selectedModel
      : undefined;
    const content = await streamAgentChat(
      {
        agent_code: code,
        thread_id: id,
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
    updateReply(content, "complete");
    if (!owned(owner) || !useAgentStore.getState().details[id]) return;
    useAgentStore.setState((current) => {
      const thread = {
        ...current.details[id].thread,
        draft: "",
        draft_revision: current.details[id].thread.draft_revision + 1,
        updated_at: new Date().toISOString(),
      };
      return {
        lists: updateList(current, code, thread),
        details: { ...current.details, [id]: { ...current.details[id], thread } },
        drafts: {
          ...current.drafts,
          [id]: {
            ...current.drafts[id],
            text: "",
            sending: false,
            pending: null,
            version: 0,
            savedVersion: 0,
          },
        },
      };
    });
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
  // 会话标题保存在本地。
  const now = new Date().toISOString();
  const row: ChatThread = {
    ...existing,
    title,
    updated_at: now,
  };
  if (owned(owner))
    useAgentStore.setState((state) => ({
      lists: updateList(state, code, row),
      details: state.details[id]
        ? {
            ...state.details,
            [id]: {
              ...state.details[id],
              thread: { ...state.details[id].thread, title: row.title },
            },
          }
        : state.details,
    }));
}
export async function removeThread(code: AgentId, id: string) {
  const owner = currentOwner();
  cancelMessage(id);
  // 仅移除当前设备上的会话。
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
