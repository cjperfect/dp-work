import { useEffect, useRef, useState } from "react";
import { useAui, useAuiState } from "@assistant-ui/react";
import { CheckIcon, CopyIcon } from "lucide-react";
import { TooltipIconButton } from "@/components/assistant-ui/elements/tooltip-icon-button";
import { copyMessageText } from "@/lib/clipboard";

/** 复制当前消息正文，原生写入成功后才显示完成反馈。 */
export function MessageCopyButton() {
  const aui = useAui();
  const id = useAuiState((state) => state.message.id);
  const hasText = useAuiState((state) =>
    state.message.content.some((part) => part.type === "text" && !!part.text),
  );
  const [copied, setCopied] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const generation = useRef(0);
  useEffect(() => {
    const scope = generation;
    setCopied(false);
    return () => {
      scope.current++;
      clearTimeout(timer.current);
    };
  }, [id]);
  async function copy() {
    const text = aui.message.getCopyText();
    if (!text) return;
    const version = generation.current;
    try {
      await copyMessageText(text);
      if (version !== generation.current) return;
      setCopied(true);
      clearTimeout(timer.current);
      timer.current = setTimeout(() => setCopied(false), 2000);
    } catch {
      /* 具体错误由剪贴板工具提示。 */
    }
  }
  return (
    <TooltipIconButton
      tooltip={copied ? "已复制" : "复制"}
      disabled={!hasText}
      onClick={() => void copy()}
    >
      {copied ? <CheckIcon /> : <CopyIcon />}
    </TooltipIconButton>
  );
}
