import type { LocalProject } from "@dp-work/protocols/desktop";
import type { AgentProject } from "@/interfaces/agent";
import { useState } from "react";
import { Folder, FolderPlus, Loader2, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import { selectLocalProject, saveLocalProject } from "@/stores/agent/agent-projects";
import { useAuthStore } from "@/stores/auth";

/** 创建项目：名称与本机目录在确认后一起保存。 */
export function CreateProjectDialog({
  open,
  onOpenChange,
  onCreated,
}: {
  open: boolean;
  onOpenChange(open: boolean): void;
  onCreated(project: AgentProject): Promise<void>;
}) {
  const owner = useAuthStore((state) => state.user?.id);
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      {open && (
        <CreateProjectForm key={owner} onClose={() => onOpenChange(false)} onCreated={onCreated} />
      )}
    </Dialog>
  );
}

function CreateProjectForm({
  onClose,
  onCreated,
}: {
  onClose(): void;
  onCreated(project: AgentProject): Promise<void>;
}) {
  const [name, setName] = useState("");
  const [folder, setFolder] = useState<LocalProject | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  async function selectFolder() {
    setBusy(true);
    setError(null);
    try {
      const selected = await selectLocalProject();
      if (selected) {
        setFolder(selected);
        if (!name.trim()) setName(selected.name);
      }
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "选择文件夹失败。");
    } finally {
      setBusy(false);
    }
  }
  async function submit() {
    if (busy || !folder || !name.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const project = await saveLocalProject({ ...folder, name: name.trim() });
      await onCreated(project);
      onClose();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "创建项目失败，请重试。");
    } finally {
      setBusy(false);
    }
  }
  return (
    <DialogContent className="gap-5 rounded-2xl p-5 sm:max-w-[520px]" showCloseButton={false}>
      <div className="flex items-center justify-between">
        <DialogTitle className="text-lg font-semibold">创建项目</DialogTitle>
        <Button variant="ghost" size="icon-xs" aria-label="关闭" disabled={busy} onClick={onClose}>
          <X className="size-4" />
        </Button>
      </div>
      <form
        className="grid gap-4"
        onSubmit={(event) => {
          event.preventDefault();
          void submit();
        }}
      >
        <div className="relative">
          <Folder className="pointer-events-none absolute top-3 left-3 size-4 text-muted-foreground" />
          <Input
            autoFocus
            aria-label="项目名称"
            placeholder="项目名称"
            value={name}
            maxLength={256}
            disabled={busy}
            className="h-10 rounded-xl pl-10"
            onChange={(event) => setName(event.target.value)}
          />
        </div>
        <div className="grid gap-2">
          <span className="text-sm font-medium">源文件夹</span>
          <div className="flex min-h-28 flex-col items-center justify-center gap-3 rounded-xl border px-4 py-5">
            {folder ? (
              <div className="flex w-full items-center gap-3">
                <Folder className="size-5 shrink-0 text-muted-foreground" />
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium">{folder.name}</p>
                  <p className="truncate text-xs text-muted-foreground" title={folder.path}>
                    {folder.path}
                  </p>
                </div>
                <Button
                  type="button"
                  size="sm"
                  variant="ghost"
                  disabled={busy}
                  onClick={() => void selectFolder()}
                >
                  更换
                </Button>
              </div>
            ) : (
              <>
                <p className="text-sm text-muted-foreground">在此电脑上添加文件夹</p>
                <Button
                  type="button"
                  variant="secondary"
                  size="sm"
                  disabled={busy || !window.desktop?.selectProjectDirectory}
                  onClick={() => void selectFolder()}
                >
                  <FolderPlus className="size-3.5" />
                  添加
                </Button>
              </>
            )}
            {!window.desktop?.selectProjectDirectory && (
              <p className="text-xs text-muted-foreground">请在桌面客户端选择本地文件夹。</p>
            )}
          </div>
        </div>
        {error && (
          <p role="alert" className="text-sm text-destructive">
            {error}
          </p>
        )}
        <div className="mt-3 flex justify-end gap-2">
          <Button type="button" variant="ghost" disabled={busy} onClick={onClose}>
            取消
          </Button>
          <Button type="submit" disabled={busy || !folder || !name.trim()}>
            {busy && <Loader2 className="size-4 animate-spin" />}创建项目
          </Button>
        </div>
      </form>
    </DialogContent>
  );
}
