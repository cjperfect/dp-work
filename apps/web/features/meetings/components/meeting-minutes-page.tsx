"use client";

import { ArrowLeft, FileText, Sparkles } from "lucide-react";
import { useNavigate } from "@tanstack/react-router";
import { Button } from "@/components/ui/button";
import { useAppStore } from "@/stores/app-store";
import { BlockNoteEditor } from "@/features/editor/components/blocknote-editor";
import { loadSession, saveSession } from "@/features/meetings/utils/session";
import type { PartialBlock } from "@blocknote/core";

/** 会议纪要页（独立页面）：基于转写内容的富文本纪要，可编辑调整后生成 */
export function MeetingMinutesPage() {
  const meetingTitle = useAppStore((s) => s.meetingTitle);
  const setMeetingStatus = useAppStore((s) => s.setMeetingStatus);
  const navigate = useNavigate();

  // 从会话恢复转写内容（结束会议前保留了 transcript）
  const session = loadSession();
  const blocks = session.transcript as PartialBlock[] | undefined;
  const hasContent = !!blocks && blocks.length > 0;

  return (
    <div className="flex h-full flex-col gap-4 px-6 py-5 md:px-8">
      {/* 顶部：返回会议列表 + 标题 + 生成纪要 */}
      <div className="flex items-center justify-between gap-3">
        <div className="flex min-w-0 items-center gap-3">
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
            <p className="text-muted-foreground text-xs">会议纪要 · 编辑完成后生成</p>
          </div>
        </div>
        <Button
          className="bg-black text-white hover:bg-black/90"
          onClick={() => {
            // 生成会议纪要：置生成中状态并返回列表页（列表展示「AI 会议纪要生成中」）
            setMeetingStatus("generating");
            navigate({ to: "/meetings" });
          }}
        >
          <Sparkles className="size-3.5" />
          生成会议纪要
        </Button>
      </div>

      {/* 纪要富文本：展示转写内容，用户可编辑调整 */}
      {hasContent ? (
        <section className="bg-card flex min-h-0 flex-1 flex-col rounded-xl border">
          <div className="min-h-0 flex-1 overflow-auto px-4 py-3">
            <BlockNoteEditor
              initialContent={blocks}
              onChange={(edited) => {
                // 编辑内容实时写回会话，供后续持久化/入库
                saveSession({ ...session, transcript: edited });
              }}
            />
          </div>
        </section>
      ) : (
        <div className="flex flex-1 flex-col items-center justify-center gap-3 rounded-xl border border-dashed">
          <div className="bg-muted flex size-12 items-center justify-center rounded-full">
            <FileText className="text-muted-foreground size-6" />
          </div>
          <p className="text-sm font-medium">暂无会议纪要内容</p>
          <p className="text-muted-foreground max-w-sm text-center text-xs">
            请先在会议进行中点「生成会议纪要」进入此页，或结束会议后从会议列表查看
          </p>
          <Button variant="outline" size="sm" onClick={() => navigate({ to: "/meetings/active" })}>
            返回进行中的会议
          </Button>
        </div>
      )}
    </div>
  );
}
