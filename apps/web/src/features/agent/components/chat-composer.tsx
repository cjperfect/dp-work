import { messageImages } from "../lib/image-attachments";
import { useEffect, useRef, useState } from "react";
import { ComposerPrimitive, useAui, useAuiState } from "@assistant-ui/react";
import { BookOpen } from "lucide-react";
import { useAgentStore } from "@/stores/agent";
import {
  enqueueFollowUp,
  initializeMessageQueue,
  saveComposerDraft,
  useAgentMessageQueue,
  waitingForApproval,
} from "@/stores/agent/agent-message-queue";

export function ChatComposerInput({ autoFocus }: { autoFocus: boolean }) {
  const aui = useAui();
  const threadId = useAuiState((state) => state.threadListItem.remoteId);
  const sending = useAgentStore((state) => (threadId ? state.sending[threadId] : false));
  const initialized = useRef<string | null>(null);
  const [inputError, setInputError] = useState<string | null>(null);
  useEffect(() => {
    initializeMessageQueue();
    if (threadId && initialized.current !== threadId) {
      initialized.current = threadId;
      const cached = useAgentMessageQueue.getState().drafts[threadId];
      if (cached !== undefined) aui.composer.setText(cached);
    }
  }, [aui, threadId]);
  return (
    <>
      <ComposerPrimitive.Input
        aria-label="聊天输入框"
        placeholder="输入消息…"
        className="aui-composer-input caret-primary placeholder:text-muted-foreground/60 max-h-48 min-h-10 w-full resize-none bg-transparent px-2.5 py-1 text-base leading-6 outline-none"
        rows={1}
        autoFocus={autoFocus}
        enterKeyHint="send"
        onChange={(event) => {
          setInputError(null);
          if (threadId) saveComposerDraft(threadId, event.target.value);
        }}
        onKeyDown={(event) => {
          if (
            event.key !== "Enter" ||
            event.shiftKey ||
            event.nativeEvent.isComposing ||
            event.nativeEvent.keyCode === 229
          )
            return;
          if (!threadId || (sending && !waitingForApproval(threadId))) return;
          event.preventDefault();
          const attachments = aui.composer.getState().attachments;
          const text =
            aui.composer.getState().text || (attachments.length ? "请查看这张图片。" : "");
          if (!text.trim()) return;
          try {
            enqueueFollowUp(threadId, text, messageImages(attachments));
            void aui.composer.clearAttachments();
            aui.composer.setText("");
            saveComposerDraft(threadId, "");
          } catch (cause) {
            setInputError(cause instanceof Error ? cause.message : "加入队列失败");
          }
        }}
      />
      {inputError && (
        <p role="alert" className="px-2.5 text-xs text-destructive">
          {inputError}
        </p>
      )}
    </>
  );
}
export function MessageKnowledgeContext() {
  const bases = useAuiState((state) => state.message.metadata.custom?.knowledge_bases);
  if (!Array.isArray(bases) || !bases.length) return null;
  return (
    <div className="mb-1.5 flex flex-wrap justify-end gap-1" aria-label="消息使用的知识库">
      {bases.map((base, index) => (
        <span
          key={String(base.id ?? index)}
          className="flex items-center gap-1 rounded-md border bg-background/60 px-1.5 py-0.5 text-[10px] text-muted-foreground"
        >
          <BookOpen className="size-2.5" />
          {String(base.name ?? "知识库")}
        </span>
      ))}
    </div>
  );
}
