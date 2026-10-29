import { useAuiState } from "@assistant-ui/react";
import { useState } from "react";
import { Undo2 } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Popover, PopoverTrigger, PopoverContent } from "@/components/ui/popover";
import { useAgentStore, undoFileChange } from "@/stores/agent";
import { FileTree } from "@/components/assistant-ui/elements/file-tree";
import { CodeDiff } from "@/components/assistant-ui/elements/code-diff";
import { HoverCard, HoverCardTrigger, HoverCardContent } from "@/components/ui/hover-card";
import type { FileChange } from "@/types/agent";

/** 展示这条回复实际完成的文件修改，按文件查看每次操作。 */
export function FileChanges() {
  const changes = useAuiState((state) => state.message.metadata.custom.file_changes) as
    FileChange[] | undefined;
  const messageId = useAuiState((state) => state.message.id);
  const running = useAuiState((state) => state.thread.isRunning);
  const threadId = useAgentStore(
    (state) =>
      Object.values(state.details).find(
        (detail) =>
          detail.messages.some((message) => message.id === messageId) ||
          detail.message_branches?.some((entry) => entry.message.id === messageId),
      )?.thread.id,
  );
  return (
    <FileChangesView
      changes={changes}
      disabled={running}
      onUndo={
        threadId
          ? async (id) => {
              await undoFileChange(threadId, id);
            }
          : undefined
      }
    />
  );
}

export function FileChangesView({
  changes,
  onUndo,
  disabled = false,
}: {
  changes?: readonly FileChange[];
  onUndo?: (id: string) => Promise<void>;
  disabled?: boolean;
}) {
  const [busy, setBusy] = useState<string | null>(null);
  const [previewPath, setPreviewPath] = useState<string | null>(null);
  const [confirming, setConfirming] = useState<string | null>(null);
  if (!changes?.length) return null;
  const groups = new Map<string, FileChange[]>();
  for (const change of changes)
    groups.set(change.path, [...(groups.get(change.path) ?? []), change]);
  return (
    <div className="my-3">
      <FileTree
        className="max-w-none rounded-xl"
        nodes={[...groups].map(([path, entries]) => ({
          path,
          name: path,
          depth: 0,
          kind: "file",
          additions: entries.reduce((n, item) => n + item.additions, 0),
          deletions: entries.reduce((n, item) => n + item.deletions, 0),
        }))}
        visibleCount={groups.size}
        totalAdditions={changes.reduce((n, item) => n + item.additions, 0)}
        totalDeletions={changes.reduce((n, item) => n + item.deletions, 0)}
        renderFileRow={(node, row) => (
          <HoverCard
            open={
              previewPath === node.path ||
              (groups.get(node.path) ?? []).some((change) => change.id === confirming)
            }
            onOpenChange={(open) => {
              if (!open && (groups.get(node.path) ?? []).some((change) => change.id === confirming))
                return;
              setPreviewPath(open ? node.path : null);
            }}
          >
            <HoverCardTrigger render={row} delay={150} closeDelay={250} />
            <HoverCardContent aria-label={`${node.path} 文件变更`}>
              <p className="mb-3 break-all text-sm font-medium">{node.path}</p>
              {(groups.get(node.path) ?? []).map((change, index) => (
                <section key={change.id} className="min-w-0 space-y-2">
                  <div className="flex items-center justify-between gap-3">
                    <p className="text-xs text-muted-foreground">
                      第 {index + 1} 次修改
                      {change.kind === "created"
                        ? " · 新建"
                        : change.kind === "deleted"
                          ? " · 删除"
                          : ""}
                    </p>
                    {change.undone ? (
                      <span className="text-xs text-muted-foreground">已撤销</span>
                    ) : change.undoable && onUndo ? (
                      <UndoChangeButton
                        disabled={disabled || busy !== null}
                        busy={busy === change.id}
                        change={change}
                        onOpenChange={(open) => setConfirming(open ? change.id : null)}
                        onConfirm={async () => {
                          setBusy(change.id);
                          try {
                            await onUndo(change.id);
                            toast.success("已撤销文件修改");
                          } catch (error) {
                            toast.error(
                              error instanceof Error ? error.message : "撤销失败，请重试。",
                            );
                          } finally {
                            setBusy(null);
                          }
                        }}
                      />
                    ) : null}
                  </div>
                  {change.undo_unavailable && (
                    <p className="text-xs text-muted-foreground">{change.undo_unavailable}</p>
                  )}
                  {change.unavailable ? (
                    <p className="text-sm text-muted-foreground">{change.unavailable}</p>
                  ) : (
                    <CodeDiff
                      className="max-w-none [&>div:last-child]:max-h-96"
                      filename={change.path.split(/[\\/]/).at(-1) ?? change.path}
                      additions={change.additions}
                      deletions={change.deletions}
                      lines={change.lines}
                      cycle={0}
                    />
                  )}
                  {change.truncated && (
                    <p className="text-xs text-muted-foreground">差异较长，仅展示前 400 行。</p>
                  )}
                </section>
              ))}
            </HoverCardContent>
          </HoverCard>
        )}
      />
    </div>
  );
}

function UndoChangeButton({
  change,
  disabled,
  busy,
  onConfirm,
  onOpenChange,
}: {
  change: FileChange;
  disabled: boolean;
  busy: boolean;
  onConfirm: () => Promise<void>;
  onOpenChange: (open: boolean) => void;
}) {
  const [open, setOpen] = useState(false);
  const changeOpen = (open: boolean) => {
    setOpen(open);
    onOpenChange(open);
  };
  return (
    <Popover open={open} onOpenChange={changeOpen}>
      <PopoverTrigger render={<Button size="xs" variant="outline" disabled={disabled} />}>
        <Undo2 className="size-3" />
        {busy ? "撤销中…" : "撤销"}
      </PopoverTrigger>
      <PopoverContent align="end" className="space-y-3">
        <p className="text-sm font-medium">撤销这次文件修改？</p>
        <p className="text-xs text-muted-foreground">
          {change.kind === "created" ? "将删除这次新建的文件。" : "将恢复修改前的文件内容。"}
          如有后续修改，将停止撤销。
        </p>
        <div className="flex justify-end gap-2">
          <Button size="sm" variant="outline" onClick={() => changeOpen(false)}>
            取消
          </Button>
          <Button
            size="sm"
            onClick={() => {
              changeOpen(false);
              void onConfirm();
            }}
          >
            确认撤销
          </Button>
        </div>
      </PopoverContent>
    </Popover>
  );
}
