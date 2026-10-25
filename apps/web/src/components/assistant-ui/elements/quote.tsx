import { useMessageQuote } from "@assistant-ui/react";
import { QuoteIcon } from "lucide-react";
import { cn } from "@/lib/utils";
import type { FC } from "react";

/**
 * 引用块（对应 assistant-ui quote 元素）：
 * 渲染当前消息引用的内容（`message.metadata.custom.quote`），
 * 无引用时返回 null。引用由选中工具栏 / Composer 引用设置，随消息发送写入。
 */
export const Quote: FC<{ className?: string }> = ({ className }) => {
  const quote = useMessageQuote();
  if (!quote) return null;

  return (
    <div
      data-slot="aui_quote"
      className={cn(
        "border-primary/30 bg-muted/40 text-muted-foreground my-2 flex items-start gap-2 rounded-lg border-s-2 py-1.5 pr-3 pl-3 text-sm",
        className,
      )}
    >
      <QuoteIcon className="mt-0.5 size-3.5 shrink-0" />
      <p className="line-clamp-3 min-w-0 italic">{quote.text}</p>
    </div>
  );
};
