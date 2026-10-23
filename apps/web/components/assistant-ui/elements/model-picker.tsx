"use client";

import { Menu } from "@base-ui/react/menu";
import { Check, ChevronDown } from "lucide-react";
import { Button } from "@/components/ui/button";
import { MODELS } from "@/constants/models";
import { useAppStore } from "@/stores/app-store";
import { cn } from "cn";
import type { FC } from "react";

/** Composer 模型选择器：展示当前模型，点击切换（对应 assistant-ui composer-model-picker 元素，0.15 无内置实现） */
export const ModelPicker: FC = () => {
  const currentModel = useAppStore((s) => s.currentModel);
  const setModel = useAppStore((s) => s.setModel);
  const current = MODELS.find((m) => m.id === currentModel) ?? MODELS[0];

  return (
    <Menu.Root>
      <Menu.Trigger
        render={
          <Button
            variant="ghost"
            size="sm"
            className="text-muted-foreground hover:text-foreground h-7 gap-1 px-1.5 text-xs"
          >
            {current.icon}
            {current.label}
            <ChevronDown className="size-3" />
          </Button>
        }
      />
      <Menu.Portal>
        <Menu.Positioner align="start" sideOffset={6}>
          <Menu.Popup className="bg-popover text-popover-foreground z-50 min-w-52 rounded-lg border p-1 shadow-lg outline-none">
            <Menu.Group>
              <Menu.GroupLabel className="text-muted-foreground px-2 py-1.5 text-xs">
                选择模型
              </Menu.GroupLabel>
              {MODELS.map((m) => (
                <Menu.Item
                  key={m.id}
                  onClick={() => setModel(m.id)}
                  className={cn(
                    "flex cursor-default items-center justify-between gap-2 rounded-md px-2 py-1.5 outline-none data-highlighted:bg-muted data-highlighted:text-foreground",
                    m.id === current.id && "text-primary",
                  )}
                >
                  <span className="flex min-w-0 items-center gap-2">
                    <span className="text-foreground shrink-0">{m.icon}</span>
                    <span className="flex flex-col">
                      <span>{m.label}</span>
                      <span className="text-muted-foreground text-xs">{m.description}</span>
                    </span>
                  </span>
                  {m.id === current.id && <Check className="size-3.5" />}
                </Menu.Item>
              ))}
            </Menu.Group>
          </Menu.Popup>
        </Menu.Positioner>
      </Menu.Portal>
    </Menu.Root>
  );
};
