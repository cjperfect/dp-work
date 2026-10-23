"use client";

import { Clock, History, Loader2, Video } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "@tanstack/react-router";
import { Button } from "@/components/ui/button";
import { useAppStore } from "@/stores/app-store";
import { MeetingCreateDialog } from "./meeting-create-dialog";

const HISTORY_MEETINGS = [
  {
    id: "m-002",
    title: "RAG 知识库架构讨论",
    date: "2026-10-21",
    summary: "已生成纪要 · 8 项待办",
  },
  {
    id: "m-003",
    title: "倍轻松小程序需求对齐",
    date: "2026-10-18",
    summary: "已生成纪要 · 3 项待办",
  },
];

export function MeetingsPage() {
  const [createOpen, setCreateOpen] = useState(false);
  const navigate = useNavigate();
  const meetingTitle = useAppStore((s) => s.meetingTitle);
  const meetingStatus = useAppStore((s) => s.meetingStatus);

  // 刚结束的会议：处于 AI 纪要生成中状态时在此展示；无动态数据时展示一条测试数据
  const generatingMeetings = [
    ...(meetingTitle && meetingStatus === "generating"
      ? [{ id: "m-live", title: meetingTitle, startedAt: "刚刚" }]
      : []),
    { id: "m-demo", title: "Q4 产品规划评审（测试数据）", startedAt: "刚刚" },
  ];

  return (
    <div className="flex w-full flex-1 flex-col gap-6 px-6 py-8 md:px-10">
      <header className="flex flex-col gap-1">
        <h1 className="text-2xl font-semibold tracking-tight">开始会议</h1>
        <p className="text-muted-foreground text-sm">
          实时转写会议内容，结束后自动生成会议纪要，并支持协同编辑与重点结构查看
        </p>
      </header>

      <section className="flex flex-col items-start gap-3">
        <Button size="lg" onClick={() => setCreateOpen(true)}>
          <Video className="size-4" />
          开始会议
        </Button>
        <p className="text-muted-foreground text-xs">
          * 点击后输入会议主题，将实时转写会议内容（UI 骨架，功能待接入）
        </p>
      </section>

      <section>
        <h2 className="mb-3 flex items-center gap-2 text-sm font-medium">
          <Clock className="text-muted-foreground size-4" />
          会议纪要 AI 生成中
        </h2>
        {generatingMeetings.length === 0 ? (
          <div className="text-muted-foreground rounded-xl border border-dashed p-6 text-center text-sm">
            暂无生成中的会议纪要
          </div>
        ) : (
          <ul className="flex flex-col gap-2">
            {generatingMeetings.map((m) => (
              <li
                key={m.id}
                className="flex items-center justify-between rounded-xl border bg-card px-4 py-3"
              >
                <div className="flex min-w-0 flex-col gap-0.5">
                  <span className="truncate text-sm font-medium">{m.title}</span>
                  <span className="text-muted-foreground text-xs">
                    会议已结束 · AI 正在生成会议纪要，稍后自动进入历史会议
                  </span>
                </div>
                <span className="bg-amber-500/10 text-amber-600 flex shrink-0 items-center gap-1.5 rounded-full px-2 py-0.5 text-xs">
                  <Loader2 className="size-3 animate-spin" />
                  AI 会议纪要生成中
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section>
        <h2 className="mb-3 flex items-center gap-2 text-sm font-medium">
          <History className="text-muted-foreground size-4" />
          历史会议
        </h2>
        <ul className="flex flex-col gap-2">
          {HISTORY_MEETINGS.map((m) => (
            <li
              key={m.id}
              className="flex items-center justify-between rounded-xl border bg-card px-4 py-3"
            >
              <div className="flex min-w-0 flex-col gap-0.5">
                <span className="truncate text-sm font-medium">{m.title}</span>
                <span className="text-muted-foreground text-xs">
                  {m.date} · {m.summary}
                </span>
              </div>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => navigate({ to: "/meetings/minutes" })}
              >
                查看会议纪要
              </Button>
            </li>
          ))}
        </ul>
      </section>

      <MeetingCreateDialog open={createOpen} onOpenChange={setCreateOpen} />
    </div>
  );
}
