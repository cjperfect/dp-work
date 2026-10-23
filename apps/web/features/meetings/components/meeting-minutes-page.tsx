"use client";

import { ArrowLeft, FileText } from "lucide-react";
import { useNavigate } from "@tanstack/react-router";
import { Button } from "@/components/ui/button";
import { useAppStore } from "@/stores/app-store";

/** 会议纪要页（独立页面）：内容待设计（协同编辑 / 邀请链接 / React Flow 重点结构等） */
export function MeetingMinutesPage() {
  const meetingTitle = useAppStore((s) => s.meetingTitle);
  const navigate = useNavigate();

  return (
    <div className="flex h-full flex-col gap-4 px-6 py-5 md:px-8">
      {/* 顶部：返回会议列表 + 标题 */}
      <div className="flex items-center gap-3">
        <Button
          variant="ghost"
          size="icon"
          aria-label="返回会议列表"
          onClick={() => navigate({ to: "/meetings" })}
        >
          <ArrowLeft className="size-4" />
        </Button>
        <div className="flex min-w-0 flex-col">
          <h1 className="truncate text-lg font-semibold">{meetingTitle ?? "未命名会议"}</h1>
          <p className="text-muted-foreground text-xs">会议纪要</p>
        </div>
      </div>

      {/* 占位：纪要内容待设计 */}
      <div className="flex flex-1 flex-col items-center justify-center gap-3 rounded-xl border border-dashed">
        <div className="bg-muted flex size-12 items-center justify-center rounded-full">
          <FileText className="text-muted-foreground size-6" />
        </div>
        <p className="text-sm font-medium">会议纪要页面待设计</p>
        <p className="text-muted-foreground max-w-sm text-center text-xs">
          将支持：纪要展示与协同编辑、发送邀请链接、React Flow 查看会议重点内容结构、一键转入知识库
        </p>
      </div>
    </div>
  );
}
