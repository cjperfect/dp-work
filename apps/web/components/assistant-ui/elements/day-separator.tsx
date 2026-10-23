"use client";

import type { FC } from "react";

const DAY_MS = 24 * 60 * 60 * 1000;

export function isDifferentDay(prev?: Date | null, current?: Date | null): boolean {
  if (!current) return false;
  if (!prev) return true;
  return prev.toDateString() !== current.toDateString();
}

function formatDayLabel(date: Date): string {
  const now = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const day = new Date(date.getFullYear(), date.getMonth(), date.getDate());
  const diffDays = Math.round((today.getTime() - day.getTime()) / DAY_MS);

  if (diffDays === 0) return "今天";
  if (diffDays === 1) return "昨天";
  if (date.getFullYear() === now.getFullYear())
    return `${date.getMonth() + 1}月${date.getDate()}日`;
  return `${date.getFullYear()}年${date.getMonth() + 1}月${date.getDate()}日`;
}

/** 消息流日期分隔线（对应 assistant-ui day-separator 元素，0.15 无内置实现，按新版样式自实现） */
export const DaySeparator: FC<{ date?: Date | null }> = ({ date }) => {
  if (!date) return null;
  return (
    <div
      data-slot="aui_day-separator"
      className="aui-day-separator my-3 flex items-center gap-3 px-2"
      aria-hidden="true"
    >
      <div className="bg-foreground/10 h-px flex-1" />
      <div className="bg-foreground/15 size-1.5 rounded-full" />
      <span className="text-muted-foreground/70 text-xs">{formatDayLabel(date)}</span>
      <div className="bg-foreground/10 h-px flex-1" />
    </div>
  );
};
