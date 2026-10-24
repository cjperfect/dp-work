"use client";

import { Mic } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "@tanstack/react-router";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { useAppStore } from "@/stores/app-store";
import { clearMeeting } from "@/features/meetings/lib/transcript-store";
import { clearSession } from "@/features/meetings/utils/session";

/** 新建会议弹窗：输入会议标题后开始（实时转写待接入 Python Sidecar） */
export function MeetingCreateDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const [title, setTitle] = useState("");
  const setMeetingTitle = useAppStore((s) => s.setMeetingTitle);
  const setMeetingStatus = useAppStore((s) => s.setMeetingStatus);
  const navigate = useNavigate();

  const handleStart = () => {
    if (!title.trim()) return;
    // 新会议：清除上一场会议的会话持久化与本地转写库
    clearSession();
    void clearMeeting(title.trim());
    setMeetingTitle(title.trim());
    setMeetingStatus("live");
    onOpenChange(false);
    setTitle("");
    navigate({ to: "/meetings/active" });
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-sm">
        <DialogHeader>
          <DialogTitle>开始会议</DialogTitle>
          <DialogDescription>输入会议主题，点击开始后实时转写内容（功能待接入）</DialogDescription>
        </DialogHeader>
        <div className="px-6 pb-2">
          <Input
            placeholder="输入会议主题，例如：Q4 产品规划评审"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && title.trim()) handleStart();
            }}
            style={{ borderRadius: 4 }}
            aria-label="会议标题"
          />
        </div>
        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            取消
          </Button>
          <Button onClick={handleStart} disabled={!title.trim()}>
            <Mic className="size-4" />
            开始会议
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
