import { useEffect, useRef, useState } from "react";
import { Download, LoaderCircle, RefreshCw } from "lucide-react";
import { toast } from "sonner";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import {
  connectDesktopUpdates,
  runDesktopUpdate,
  useDesktopUpdates,
} from "@/stores/desktop-updates";

export function DesktopUpdates() {
  const { open, update, error } = useDesktopUpdates();
  const [confirm, setConfirm] = useState(false);
  const notices = useRef(new Set<string>());
  useEffect(connectDesktopUpdates, []);
  useEffect(() => {
    if (!update?.availableVersion || !["available", "downloaded"].includes(update.status)) return;
    const key = `${update.status}:${update.availableVersion}`;
    if (notices.current.has(key)) return;
    notices.current.add(key);
    toast.info(
      update.status === "available"
        ? `发现新版本 ${update.availableVersion}，可在用户菜单“检查更新”中下载。`
        : `版本 ${update.availableVersion} 已下载，可在用户菜单中重启安装。`,
    );
  }, [update]);
  const status = update?.status;
  const busy = status === "checking" || status === "downloading" || status === "installing";
  const action =
    status === "available"
      ? "download"
      : status === "downloaded"
        ? "install"
        : status === "error"
          ? (update?.retry ?? "check")
          : "check";
  const disabled = busy || status === "disabled";
  function close(value: boolean) {
    if (status === "installing") return;
    useDesktopUpdates.setState({ open: value });
    if (!value) setConfirm(false);
  }
  return (
    <Dialog open={open} onOpenChange={close}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{confirm ? "重启并安装更新？" : "应用更新"}</DialogTitle>
          <DialogDescription>
            {confirm
              ? "应用将重启。请先保存编辑内容、结束会议并停止正在执行的任务。"
              : "从 GitHub Releases 获取正式版本，下载后由你选择重启安装。"}
          </DialogDescription>
        </DialogHeader>
        {!confirm && (
          <div className="space-y-3 py-2 text-sm">
            <div className="flex justify-between">
              <span className="text-muted-foreground">当前版本</span>
              <span>{update?.currentVersion ?? "读取中…"}</span>
            </div>
            {update?.availableVersion && (
              <div className="flex justify-between">
                <span className="text-muted-foreground">可用版本</span>
                <span>{update.availableVersion}</span>
              </div>
            )}
            {status === "checking" && (
              <p className="flex items-center gap-2 text-muted-foreground">
                <LoaderCircle className="size-4 animate-spin" />
                正在检查更新…
              </p>
            )}
            {status === "downloading" && (
              <div className="space-y-2">
                <p>正在下载 {Math.round(update?.percent ?? 0)}%</p>
                <div
                  role="progressbar"
                  aria-label="更新下载进度"
                  aria-valuenow={Math.round(update?.percent ?? 0)}
                  aria-valuemin={0}
                  aria-valuemax={100}
                  className="h-1.5 overflow-hidden rounded-full bg-muted"
                >
                  <div
                    className="h-full bg-primary transition-[width]"
                    style={{ width: `${update?.percent ?? 0}%` }}
                  />
                </div>
              </div>
            )}
            {status === "downloaded" && (
              <p className="text-muted-foreground">更新已下载并完成校验，重启后生效。</p>
            )}
            {status === "installing" && (
              <p className="flex items-center gap-2 text-muted-foreground">
                <LoaderCircle className="size-4 animate-spin" />
                正在准备安装更新…
              </p>
            )}
            {(error || update?.message) && (
              <p
                role={error || status === "error" ? "alert" : "status"}
                className={
                  error || status === "error" ? "text-destructive" : "text-muted-foreground"
                }
              >
                {error ?? update?.message}
              </p>
            )}
          </div>
        )}
        <DialogFooter>
          <Button variant="outline" disabled={status === "installing"} onClick={() => close(false)}>
            稍后
          </Button>
          <Button
            disabled={disabled}
            onClick={() => {
              if (action === "install" && !confirm) setConfirm(true);
              else void runDesktopUpdate(action);
            }}
          >
            {busy ? (
              <LoaderCircle className="size-4 animate-spin" />
            ) : action === "download" ? (
              <Download className="size-4" />
            ) : (
              <RefreshCw className="size-4" />
            )}
            {status === "installing"
              ? "正在安装"
              : action === "install"
                ? confirm
                  ? "确认重启"
                  : "重启安装"
                : action === "download"
                  ? "下载更新"
                  : "检查更新"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
