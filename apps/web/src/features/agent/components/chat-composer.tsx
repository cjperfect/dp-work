import { useEffect, useRef, useState } from "react";
import { ComposerPrimitive, useAui, useAuiState } from "@assistant-ui/react";
import { BookOpen } from "lucide-react";
import { Button } from "@/components/ui/button";
import { flushDraft, sendMessage, setDraftText, useAgentStore } from "@/stores/agent";
import { useAgentCode } from "@/features/agent/hooks/use-agent-code";

export function ChatComposerInput({ autoFocus }: { autoFocus: boolean }) {
  const aui = useAui();
  const code = useAgentCode();
  const threadId = useAgentStore((state) => state.selected[code]);
  const draft = useAgentStore((state) => (threadId ? state.drafts[threadId] : undefined));
  const initialized = useRef(false);
  useEffect(() => {
    if (!initialized.current && draft) {
      initialized.current = true;
      aui.composer.setText(draft.text);
    }
  }, [aui, draft]);
  useEffect(() => {
    if (draft?.error && !draft.sending && aui.composer.getState().text === "" && draft.text)
      aui.composer.setText(draft.text);
  }, [aui, draft?.error, draft?.sending, draft?.text]);
  return (
    <ComposerPrimitive.Input
      aria-label="聊天输入框"
      placeholder="输入消息…"
      className="aui-composer-input caret-primary placeholder:text-muted-foreground/60 max-h-48 min-h-10 w-full resize-none bg-transparent px-2.5 py-1 text-base leading-6 outline-none"
      rows={1}
      autoFocus={autoFocus}
      enterKeyHint="send"
      onChange={(event) => {
        if (threadId) setDraftText(threadId, event.target.value);
      }}
    />
  );
}
export function ChatSaveError() {
  const aui = useAui();
  const code = useAgentCode();
  const state = useAgentStore();
  const id = state.selected[code];
  const draft = id ? state.drafts[id] : undefined;
  const [error, setError] = useState<string | null>(null);
  if (!draft?.error && !error) return null;
  return (
    <div className="px-2.5 pb-1 text-xs leading-5 text-destructive" role="alert">
      {(draft?.error || error) && (
        <div className="mt-1 flex items-center gap-2 text-destructive">
          <span>{error ?? draft?.error}</span>
          <Button
            size="xs"
            variant="outline"
            onClick={() => {
              if (id)
                void (draft?.pending ? sendMessage(code, id, draft.text) : flushDraft(code, id))
                  .then(() => {
                    setError(null);
                    if (draft?.pending) aui.composer.setText("");
                  })
                  .catch((cause) => setError(cause instanceof Error ? cause.message : "重试失败"));
            }}
          >
            重试
          </Button>
        </div>
      )}
    </div>
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
