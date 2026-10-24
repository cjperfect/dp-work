"use client";

import { Clock, FileQuestion, History, Loader2, Video } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "@tanstack/react-router";
import { Button } from "@/components/ui/button";
import { useAppStore } from "@/stores/app-store";
import { MeetingCreateDialog } from "./meeting-create-dialog";
import { saveSession } from "@/features/meetings/utils/session";
import {
  GENERATING_DEMO_MEETING,
  HISTORY_MEETINGS,
  UNGENERATED_MEETINGS,
} from "@/features/meetings/constants/meeting";

export function MeetingsPage() {
  const [createOpen, setCreateOpen] = useState(false);
  const navigate = useNavigate();
  const meetingTitle = useAppStore((s) => s.meetingTitle);
  const setMeetingTitle = useAppStore((s) => s.setMeetingTitle);
  const meetingStatus = useAppStore((s) => s.meetingStatus);

  // 刚结束的会议：处于 AI 纪要生成中状态时在此展示；无动态数据时展示一条测试数据
  const generatingMeetings = [
    ...(meetingStatus === "generating"
      ? [{ id: "m-live", title: meetingTitle ?? "未命名会议", startedAt: "刚刚" }]
      : []),
    GENERATING_DEMO_MEETING,
  ];

  const ungeneratedMeetings = UNGENERATED_MEETINGS;

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
          <FileQuestion className="text-muted-foreground size-4" />
          未生成
        </h2>
        {ungeneratedMeetings.length === 0 ? (
          <div className="text-muted-foreground rounded-xl border border-dashed p-6 text-center text-sm">
            暂无未生成纪要的会议
          </div>
        ) : (
          <ul className="flex flex-col gap-2">
            {ungeneratedMeetings.map((m) => (
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
                  variant="outline"
                  size="sm"
                  onClick={() => {
                    // 查看并调整：载入该会议转写内容到纪要编辑页
                    setMeetingTitle(m.title);
                    if (m.transcript) {
                      saveSession({
                        startTs: Date.now(),
                        pausedSec: 0,
                        isPaused: false,
                        transcript: m.transcript,
                      });
                    }
                    navigate({ to: "/meetings/minutes" });
                  }}
                >
                  查看
                </Button>
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
