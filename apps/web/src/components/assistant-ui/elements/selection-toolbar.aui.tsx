import { SelectionToolbarPrimitive } from "@assistant-ui/react";
import { QuoteIcon } from "lucide-react";
import type { FC } from "react";

/**
 * 选中工具栏（引用入口）：在消息内选中文本后，浮层显示「引用」按钮，
 * 点击将选中内容设为 Composer 引用（对应 assistant-ui quote 元素链路）。
 */
export const SelectionToolbar: FC = () => (
  <SelectionToolbarPrimitive.Root className="z-50">
    <div className="bg-popover text-popover-foreground flex items-center gap-0.5 rounded-lg border p-1 shadow-lg">
      <SelectionToolbarPrimitive.Quote
        className="hover:bg-muted flex cursor-default items-center gap-1 rounded-md px-2 py-1.5 text-xs font-medium outline-none select-none"
        aria-label="引用选中文本"
      >
        <QuoteIcon className="size-3.5" />
        引用
      </SelectionToolbarPrimitive.Quote>
    </div>
  </SelectionToolbarPrimitive.Root>
);
