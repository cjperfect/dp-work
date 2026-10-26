import { useEffect, useMemo, useRef, type PropsWithChildren } from "react";
import {
  AssistantRuntimeProvider,
  useAui,
  useAuiState,
  useExternalStoreRuntime,
  useRemoteThreadListRuntime,
  type AppendMessage,
  type RemoteThreadListAdapter,
  type ThreadMessageLike,
} from "@assistant-ui/react";
import { createAssistantStream } from "assistant-stream";
import { useAuthStore } from "@/stores/auth";
import { useAppStore } from "@/stores/app";
import { useAgentCode } from "@/features/agent/hooks/use-agent-code";
import {
  cancelMessage,
  createThread,
  getThreadAgentCode,
  removeThread,
  renameThread,
  editMessage,
  sendMessage,
  useAgentStore,
} from "@/stores/agent";
import type { ChatThread } from "@/types/agent";

/**
 * 会话历史 adapter：列表与 CRUD 暂存 agent-store，模型执行走 API。
 * 保持模块级稳定引用（assistant-ui 要求 adapter 跨渲染稳定），方法内用
 * getState() 读取最新状态，reload 时才重新 list()。
 */
const threadListAdapter: RemoteThreadListAdapter = {
  async list() {
    const state = useAgentStore.getState();
    if (state.owner !== useAuthStore.getState().user?.id) return { threads: [] };
    // 汇总当前账号下全部 Agent 的会话。
    const threads = Object.values(state.lists).flatMap((rows) =>
      (rows ?? []).map((row) => ({
        status: "regular" as const,
        remoteId: row.id,
        title: row.title,
        lastMessageAt: row.updated_at ? new Date(row.updated_at) : undefined,
      })),
    );
    return { threads };
  },
  async initialize() {
    // 本地数据源直接采纳 runtime 传入的 localId 作为业务 id
    const code = useAppStore.getState().agentId;
    const id = await createThread(code);
    useAppStore.getState().bindThreadAgent(id, code);
    return { remoteId: id };
  },
  async fetch(remoteId) {
    const state = useAgentStore.getState();
    const row = (Object.values(state.lists) as ChatThread[][])
      .flat()
      .find((t) => t.id === remoteId);
    if (!row) throw new Error("会话不存在。");
    return {
      status: "regular" as const,
      remoteId,
      title: row.title,
      lastMessageAt: row.updated_at ? new Date(row.updated_at) : undefined,
    };
  },
  async rename(remoteId, title) {
    const code = getThreadAgentCode(remoteId);
    if (code) await renameThread(code, remoteId, title);
  },
  async archive() {
    // 本地暂不归档（界面已移除归档入口）
  },
  async delete(remoteId) {
    const code = getThreadAgentCode(remoteId);
    if (code) await removeThread(code, remoteId);
  },
  async generateTitle() {
    // 首条消息已在 sendMessage 中本地命名，不再流式生成标题
    return createAssistantStream(async () => {});
  },
};

/** 每个线程一个 ExternalStore runtime：消息来自 agent-store（本地）。 */
function useThreadRuntimeHook() {
  const aui = useAui();
  const remoteId = useAuiState((s) => s.threadListItem.remoteId);
  const detail = useAgentStore((state) => (remoteId ? state.details[remoteId] : undefined));
  const draft = useAgentStore((state) => (remoteId ? state.drafts[remoteId] : undefined));
  const messages = useMemo<ThreadMessageLike[]>(
    () =>
      detail?.messages.map((row) => ({
        id: row.id,
        role: row.role,
        content: row.content,
        createdAt: new Date(row.created_at),
        metadata: {
          custom: {
            knowledge_bases: row.context.knowledge_bases,
            skills: row.context.skills,
            agent: row.context.agent,
          },
        },
      })) ?? [],
    [detail?.messages],
  );
  return useExternalStoreRuntime<ThreadMessageLike>({
    messages,
    convertMessage: (message) => message,
    // 空态（remoteId 未定）不禁用：用户输入即触发 onNew → initialize；
    // 仅发送中禁用，避免重复提交。
    isLoading: !!remoteId && !detail,
    isDisabled: !!draft?.sending,
    isRunning: !!draft?.sending,
    onCancel: async () => {
      if (remoteId) cancelMessage(remoteId);
    },
    onEdit: async (message: AppendMessage) => {
      const id = aui.threadListItem.getState().remoteId;
      if (!id || !message.sourceId) throw new Error("会话或消息不存在，请重新加载。");
      if (message.attachments?.length) throw new Error("附件上传尚未接入。");
      const text = message.content
        .filter((part) => part.type === "text")
        .map((part) => part.text)
        .join("\n");
      await editMessage(
        getThreadAgentCode(id) ?? useAppStore.getState().agentId,
        id,
        message.sourceId,
        text,
      );
    },
    onNew: async (message: AppendMessage) => {
      if (message.attachments?.length) throw new Error("附件上传尚未接入。");
      let id = aui.threadListItem.getState().remoteId;
      if (!id) {
        const init = await aui.threadListItem.initialize();
        id = init.remoteId;
      }
      const text = message.content
        .filter((part) => part.type === "text")
        .map((part) => part.text)
        .join("\n");
      await sendMessage(getThreadAgentCode(id) ?? useAppStore.getState().agentId, id, text);
    },
  });
}

/**
 * 本地 store 的会话列表变化（新建/重命名/删除/首条消息命名）时刷新
 * RemoteThreadList 的列表元数据；reload 保留当前打开的线程。
 */
function ThreadListReloadOnChange() {
  const aui = useAui();
  const owner = useAuthStore((state) => state.user?.id);
  const lists = useAgentStore((state) => state.lists);
  const first = useRef(true);
  useEffect(() => {
    if (!owner) return;
    if (first.current) {
      first.current = false;
      return;
    }
    void aui.threads.reload().catch(() => {});
  }, [aui, owner, lists]);
  return null;
}

export function ChatRuntime({ children }: PropsWithChildren) {
  const code = useAgentCode();
  // 仅取首次挂载时已选中的会话作为初始线程（不订阅，避免与 runtime
  // 内部的线程切换冲突）；刷新页面后恢复上次打开的会话。
  const initialRef = useRef<string | null | undefined>(undefined);
  if (initialRef.current === undefined) {
    const owner = useAuthStore.getState().user?.id;
    const state = useAgentStore.getState();
    const selected = owner && state.owner === owner ? state.selected[code] : undefined;
    initialRef.current =
      selected &&
      Object.values(state.lists).some((rows) => rows?.some((row) => row.id === selected))
        ? selected
        : null;
  }
  const runtime = useRemoteThreadListRuntime({
    runtimeHook: useThreadRuntimeHook,
    adapter: threadListAdapter,
    ...(initialRef.current ? { initialThreadId: initialRef.current } : {}),
  });
  return (
    <AssistantRuntimeProvider runtime={runtime}>
      <ThreadListReloadOnChange />
      {children}
    </AssistantRuntimeProvider>
  );
}
