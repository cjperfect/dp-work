import { useAuiState } from "@assistant-ui/react";
import { Loader2 } from "lucide-react";
import { useAgentStore } from "@/stores/agent";

/** 当前会话实际压缩上下文时，在输入框上方保持可见。 */
export function CompactionNotice() {
  const id = useAuiState((state) => state.threadListItem.remoteId);
  const optimizing = useAgentStore((state) =>
    id
      ? (state.details[id]?.messages.some(
          (row) => row.status === "streaming" && row.context.compaction?.status === "running",
        ) ?? false)
      : false,
  );
  if (!optimizing) return null;
  return (
    <div
      role="status"
      aria-live="polite"
      className="bg-muted/60 text-muted-foreground mb-2 flex items-center gap-2 rounded-lg border px-3 py-2 text-xs"
    >
      <Loader2 aria-hidden className="size-3.5 shrink-0 animate-spin motion-reduce:animate-none" />
      <span>正在优化对话，请稍候，可能需要几分钟</span>
    </div>
  );
}
