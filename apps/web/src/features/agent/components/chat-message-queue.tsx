import { messageImages } from "../lib/image-attachments";
import { useState } from "react";
import { useAui, useAuiState } from "@assistant-ui/react";
import { ArrowUpToLine, ListEnd, X, Play } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useAgentStore } from "@/stores/agent";
import { useAgentApprovalStore } from "@/stores/agent/agent-approvals";
import {
  useAgentMessageQueue,
  enqueueFollowUp,
  removeQueuedMessage,
  guideQueuedMessage,
  continueMessageQueue,
  saveComposerDraft,
} from "@/stores/agent/agent-message-queue";

const EMPTY: never[] = [];
export function ChatMessageQueue() {
  const id = useAuiState((s) => s.threadListItem.remoteId);
  const rows = useAgentMessageQueue((s) => (id ? (s.items[id] ?? EMPTY) : EMPTY));
  const paused = useAgentMessageQueue((s) => (id ? s.paused[id] : false));
  const error = useAgentMessageQueue((s) => (id ? s.errors[id] : null));
  const sending = useAgentStore((s) => (id ? s.sending[id] : false));
  const waiting = useAgentApprovalStore((s) =>
    id ? s.entries[id]?.items.some((row) => row.actionable) : false,
  );
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  if (!id || !rows.length) return null;
  return (
    <div className="mb-2 rounded-xl border bg-muted/30 p-2" aria-label="待发送消息">
      <div className="mb-1 flex items-center justify-between px-1 text-xs text-muted-foreground">
        <span>
          待处理 · {rows.length}
          {waiting
            ? " · 请先处理审批"
            : paused
              ? " · 已暂停"
              : rows.some((row) => row.mode === "steering")
                ? " · 引导将在下一轮生效"
                : ""}
        </span>
        {!sending && !waiting && (
          <Button variant="ghost" size="xs" onClick={() => continueMessageQueue(id)}>
            <Play className="size-3" />
            继续发送
          </Button>
        )}
      </div>
      <div className="max-h-36 overflow-y-auto">
        {rows.map((row) => (
          <div
            key={row.id}
            className="flex items-center gap-2 rounded-lg px-2 py-1.5 hover:bg-muted"
          >
            <ListEnd className="size-3.5 shrink-0 text-muted-foreground" />
            <span className="min-w-0 flex-1 truncate text-sm" title={row.text}>
              {row.text}
            </span>
            <Button
              variant="ghost"
              size="xs"
              disabled={busy || waiting || row.mode === "steering" || !!row.images?.length}
              title={
                waiting
                  ? "请先处理工具审批，恢复执行后即可引导"
                  : row.mode === "steering"
                    ? "已提交引导，等待下一轮生效"
                    : busy
                      ? "正在提交引导"
                      : "在下一轮模型调用前补充指令，保留当前执行进度"
              }
              onClick={() => {
                setBusy(true);
                setFailure(null);
                void guideQueuedMessage(id, row.id)
                  .catch((cause) => setFailure(cause instanceof Error ? cause.message : "引导失败"))
                  .finally(() => setBusy(false));
              }}
            >
              <ArrowUpToLine className="size-3.5" />
              {row.mode === "steering" ? "等待生效" : "引导"}
            </Button>
            <Button
              variant="ghost"
              size="icon-xs"
              aria-label={`取消排队：${row.text}`}
              disabled={busy || row.mode === "steering"}
              onClick={() => removeQueuedMessage(id, row.id)}
            >
              <X className="size-3.5" />
            </Button>
          </div>
        ))}
      </div>
      {(error || failure) && (
        <p role="alert" className="px-2 py-1 text-xs text-destructive">
          {failure ?? error}
        </p>
      )}
    </div>
  );
}

/** 回复期间保留停止按钮，另提供排队或引导当前运行。 */
export function ChatQueueActions() {
  const aui = useAui();
  const id = useAuiState((s) => s.threadListItem.remoteId);
  const text = useAuiState((s) => s.composer.text);
  const hasImages = useAuiState((s) => s.composer.attachments.length > 0);
  const sending = useAgentStore((s) => (id ? s.sending[id] : false));
  const waiting = useAgentApprovalStore((s) =>
    id ? s.entries[id]?.items.some((row) => row.actionable) : false,
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  if (!id || (!sending && !waiting) || (!text.trim() && !hasImages)) return null;
  async function submit(guide: boolean) {
    if (!id || busy) return;
    setBusy(true);
    setError(null);
    try {
      const images = messageImages(aui.composer.getState().attachments);
      const messageId = enqueueFollowUp(id, text || "请查看这张图片。", images);
      await aui.composer.clearAttachments();
      aui.composer.setText("");
      saveComposerDraft(id, "");
      if (guide) await guideQueuedMessage(id, messageId);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "消息发送失败");
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      {error && (
        <span role="alert" className="max-w-40 text-xs text-destructive">
          {error}
        </span>
      )}
      <Button
        type="button"
        variant="ghost"
        size="sm"
        disabled={busy}
        onClick={() => void submit(false)}
      >
        <ListEnd className="size-4" />
        排队
      </Button>
      <Button
        type="button"
        variant="outline"
        size="sm"
        disabled={busy || waiting || hasImages}
        title={
          waiting
            ? "请先处理工具审批，恢复执行后即可引导"
            : busy
              ? "正在提交引导"
              : "在下一轮模型调用前补充指令"
        }
        onClick={() => void submit(true)}
      >
        <ArrowUpToLine className="size-4" />
        引导
      </Button>
    </>
  );
}
