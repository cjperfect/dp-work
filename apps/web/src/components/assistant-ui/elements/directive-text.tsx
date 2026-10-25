import { useAuiState } from "@assistant-ui/react";
import { CommandIcon } from "lucide-react";
import { cn } from "cn";
import type { FC } from "react";

/**
 * 指令文本（对应 assistant-ui directive-text 元素，0.15 无内置实现）：
 * 当消息带有 `metadata.custom.directive` 指令时，在消息内容上方渲染指令块。
 * 指令数据由后端/运行时写入，如 voice 指令、系统注入的方向性指示（待接入）。
 */
export const DirectiveText: FC<{ className?: string }> = ({ className }) => {
  const directive = useAuiState((s) => s.message.metadata.custom.directive as string | undefined);
  if (!directive) return null;

  return (
    <div
      data-slot="aui_directive-text"
      className={cn(
        "aui-directive-text text-muted-foreground/70 mb-1 flex items-center gap-1.5 px-1 text-xs",
        className,
      )}
    >
      <CommandIcon className="size-3.5 shrink-0" />
      <span className="truncate italic">{directive}</span>
    </div>
  );
};
