import { useRef, useState } from "react";
import { useNavigate } from "@tanstack/react-router";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog";
import { useAuthStore } from "@/stores/auth";
import { createMeeting } from "@/apis/meetings";
import { cacheCreated } from "@/stores/meetings";
function localTime() {
  const date = new Date();
  return new Date(date.getTime() - date.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
}
export function MeetingCreateDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const [title, setTitle] = useState("");
  const [time, setTime] = useState(localTime);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const lock = useRef(false);
  const navigate = useNavigate();
  const accountId = useAuthStore((s) => s.user?.id);
  async function start(event: React.FormEvent) {
    event.preventDefault();
    if (lock.current || !title.trim()) return;
    lock.current = true;
    setBusy(true);
    setError(null);
    try {
      if (!accountId) throw new Error("请先登录。");
      const workspace = await createMeeting(accountId, {
        id: crypto.randomUUID(),
        title: title.trim(),
        scheduled_at: new Date(time).toISOString(),
      });
      await cacheCreated(workspace);
      onOpenChange(false);
      setTitle("");
      await navigate({ to: "/meetings/active", search: { id: workspace.meeting.id } });
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "创建失败");
    } finally {
      setBusy(false);
      lock.current = false;
    }
  }
  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!busy) onOpenChange(next);
      }}
    >
      <DialogContent showCloseButton={!busy}>
        <DialogHeader>
          <DialogTitle>开始一场会议</DialogTitle>
          <DialogDescription>填写会议标题和时间，会议内容由 ASR 自动转写。</DialogDescription>
        </DialogHeader>
        <form onSubmit={(event) => void start(event)} className="grid gap-4">
          <label className="grid gap-2 text-sm">
            会议标题
            <Input
              aria-label="会议标题"
              required
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="例如：产品规划评审"
            />
          </label>
          <label className="grid gap-2 text-sm">
            会议时间
            <Input
              aria-label="会议时间"
              type="datetime-local"
              required
              value={time}
              onChange={(e) => setTime(e.target.value)}
            />
          </label>
          {error && (
            <p role="alert" className="text-sm text-destructive">
              {error}
            </p>
          )}
          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              disabled={busy}
              onClick={() => onOpenChange(false)}
            >
              取消
            </Button>
            <Button type="submit" disabled={busy || !title.trim()}>
              {busy ? "创建中…" : "开始记录"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
