import {
  enqueueFollowUp,
  saveComposerDraft,
  waitingForApproval,
  useAgentMessageQueue,
} from "@/stores/agent-message-queue";
import { useEffect, useMemo, useRef, type PropsWithChildren } from "react";
import {
  AssistantRuntimeProvider,
  ExportedMessageRepository,
  useAui,
  useAuiState,
  useExternalStoreRuntime,
  useRemoteThreadListRuntime,
  type AppendMessage,
  type RemoteThreadListAdapter,
  type ThreadMessage,
} from "@assistant-ui/react";
import { createAssistantStream } from "assistant-stream";
import { toast } from "sonner";
import { useAuthStore } from "@/stores/auth";
import { useAppStore } from "@/stores/app";
import { useAgentCode } from "@/features/agent/hooks/use-agent-code";
import {
  loadAgents,
  selectThreadById,
  cancelMessage,
  createThread,
  getThreadAgentCode,
  generateThreadTitle,
  preserveMessageBranches,
  collectMessageBranches,
  selectMessageBranch,
  removeThread,
  renameThread,
  editMessage,
  regenerateMessage,
  sendMessage,
  setDraftText,
  useAgentStore,
} from "@/stores/agent";
import { readRuntimeBranches, toRuntimeMessage } from "@/features/agent/lib/message-branches";
import type { ChatThread } from "@/types/agent";
import { imageAttachmentAdapter, messageImages } from "../lib/image-attachments";

/**
 * 会话历史 adapter：列表与 CRUD 保存到 API / PG，store 只缓存当前页面。
 * 保持模块级稳定引用（assistant-ui 要求 adapter 跨渲染稳定），方法内用
 * getState() 读取最新状态，reload 时才重新 list()。
 */
const threadListAdapter: RemoteThreadListAdapter = {
  async list() {
    await loadAgents();
    const state = useAgentStore.getState();
    if (state.owner !== useAuthStore.getState().user?.id) return { threads: [] };
    // 汇总当前账号下全部 Agent 的会话。
    const threads = Object.values(state.lists).flatMap((rows) =>
      (rows ?? [])
        .filter((row) => row.has_history)
        .map((row) => ({
          status: "regular" as const,
          remoteId: row.id,
          title: row.title_source === "pending" ? undefined : row.title,
          lastMessageAt: row.updated_at ? new Date(row.updated_at) : undefined,
        })),
    );
    return { threads };
  },
  async initialize() {
    // 由 API 幂等创建会话并返回业务 ID
    const code = useAppStore.getState().agentId;
    const id = await createThread(code);
    useAppStore.getState().bindThreadAgent(id, code);
    return { remoteId: id };
  },
  async fetch(remoteId) {
    const state = useAgentStore.getState();
    const row =
      state.details[remoteId]?.thread ??
      (Object.values(state.lists) as ChatThread[][]).flat().find((t) => t.id === remoteId);
    if (!row) throw new Error("会话不存在。");
    return {
      status: "regular" as const,
      remoteId,
      title: row.title_source === "pending" ? undefined : row.title,
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
  async generateTitle(remoteId) {
    return createAssistantStream(async (controller) => {
      const title = await generateThreadTitle(remoteId);
      if (title) controller.appendText(title);
    });
  },
};

/** 每个线程一个 ExternalStore runtime：消息来自 API，在 agent-store 中缓存。 */
function useThreadRuntimeHook() {
  const aui = useAui();
  const remoteId = useAuiState((s) => s.threadListItem.remoteId);
  const detail = useAgentStore((state) => (remoteId ? state.details[remoteId] : undefined));
  const draft = useAgentStore((state) => (remoteId ? state.drafts[remoteId] : undefined));
  useEffect(() => {
    if (
      remoteId &&
      detail?.thread.title_source === "pending" &&
      !draft?.sending &&
      detail.messages.some(
        (row) => row.role === "assistant" && row.status === "complete" && row.content.trim(),
      )
    ) {
      void generateThreadTitle(remoteId);
    }
  }, [remoteId, detail?.thread.title_source, detail?.messages, draft?.sending]);
  useEffect(() => {
    if (remoteId && !useAgentStore.getState().details[remoteId])
      void selectThreadById(remoteId).catch((error) =>
        useAgentStore.setState({
          error: error instanceof Error ? error.message : "无法读取会话。",
        }),
      );
  }, [remoteId]);
  const messages = useMemo<ThreadMessage[]>(
    () => detail?.messages.map(toRuntimeMessage) ?? [],
    [detail?.messages],
  );
  const repository = useMemo(
    () =>
      detail?.message_branches
        ? ExportedMessageRepository.fromBranchableArray(
            collectMessageBranches(detail.messages, detail.message_branches).map((entry) => ({
              parentId: entry.parentId,
              message: toRuntimeMessage(entry.message),
            })),
            { headId: detail.messages.at(-1)?.id ?? null },
          )
        : undefined,
    [detail?.messages, detail?.message_branches],
  );
  const readBranches = () => {
    const id = aui.threadListItem.getState().remoteId;
    const current = id ? useAgentStore.getState().details[id] : undefined;
    return current
      ? readRuntimeBranches(
          aui.thread().export().messages,
          collectMessageBranches(current.messages, current.message_branches),
        )
      : [];
  };
  return useExternalStoreRuntime({
    adapters: { attachments: imageAttachmentAdapter },
    messages,
    ...(repository ? { messageRepository: repository } : {}),
    setMessages: (selected) => {
      const id = aui.threadListItem.getState().remoteId;
      if (id)
        selectMessageBranch(
          id,
          selected.map((message) => message.id),
          readBranches(),
        );
    },
    // 回复与审批期间仍允许编写下一条消息，提交由会话队列串行调度。
    isLoading: !!remoteId && !detail,
    isDisabled: false,
    isRunning: !!draft?.sending,
    onCancel: async () => {
      if (remoteId) cancelMessage(remoteId);
    },
    onEdit: async (message: AppendMessage) => {
      const id = aui.threadListItem.getState().remoteId;
      if (!id || !message.sourceId) throw new Error("会话或消息不存在，请重新加载。");
      const images = messageImages(message.attachments);
      const text =
        message.content
          .filter((part) => part.type === "text")
          .map((part) => part.text)
          .join("\n") || (images.length ? "请查看这张图片。" : "");
      preserveMessageBranches(id, readBranches());
      await editMessage(
        getThreadAgentCode(id) ?? useAppStore.getState().agentId,
        id,
        message.sourceId,
        text,
        images,
      );
    },
    onReload: async (parentId) => {
      const id = aui.threadListItem.getState().remoteId;
      if (!id) throw new Error("会话尚未加载。");
      preserveMessageBranches(id, readBranches());
      try {
        await regenerateMessage(
          getThreadAgentCode(id) ?? useAppStore.getState().agentId,
          id,
          parentId,
        );
      } catch (cause) {
        toast.error(cause instanceof Error ? cause.message : "重新生成失败，请重试。");
        throw cause;
      }
    },
    onNew: async (message: AppendMessage) => {
      const images = messageImages(message.attachments);
      let id = aui.threadListItem.getState().remoteId;
      if (!id) {
        const init = await aui.threadListItem.initialize();
        id = init.remoteId;
      }
      const text =
        message.content
          .filter((part) => part.type === "text")
          .map((part) => part.text)
          .join("\n") || (images.length ? "请查看这张图片。" : "");
      if (
        useAgentStore.getState().drafts[id]?.sending ||
        waitingForApproval(id) ||
        useAgentMessageQueue.getState().items[id]?.length
      ) {
        enqueueFollowUp(id, text, images);
        setDraftText(id, "");
        saveComposerDraft(id, "");
      } else {
        saveComposerDraft(id, "");
        // 及时结束 composer submission，避免回复完成后清除用户新输入的文字。
        void sendMessage(getThreadAgentCode(id) ?? useAppStore.getState().agentId, id, text, {
          images,
        }).catch(() => {});
      }
    },
  });
}

/**
 * 会话列表变化（新建/重命名/删除/首条消息命名）时刷新
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

/** API 列表异步加载后，恢复当前 Agent 上次选中的会话。 */
function RestoreThreadSelection() {
  const aui = useAui();
  const auiRef = useRef(aui);
  const owner = useAuthStore((state) => state.user?.id);
  const code = useAgentCode();
  const selected = useAgentStore((state) => state.selected[code]);
  const loading = useAgentStore((state) => state.loading);
  const restored = useRef<string | null>(null);
  useEffect(() => {
    auiRef.current = aui;
  }, [aui]);
  useEffect(() => {
    const key = `${owner}:${code}`;
    if (loading || !owner || !selected || restored.current === key) return;
    let alive = true;
    void auiRef.current.threads
      .getLoadThreadsPromise()
      .then(() => {
        if (alive) {
          restored.current = key;
          auiRef.current.threads.switchToThread(selected);
        }
      })
      .catch(() => {});
    return () => {
      alive = false;
    };
  }, [owner, code, loading, selected]);
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
      <RestoreThreadSelection />
      {children}
    </AssistantRuntimeProvider>
  );
}
