import type { KbFile } from "@/interfaces/knowledge";
import { useRef, useState } from "react";
import { Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Popover, PopoverContent } from "@/components/ui/popover";
import { deleteKnowledgeDocumentRequest } from "@/apis/knowledge";
import { useAuthStore } from "@/stores/auth";
import { localAccountId } from "@/features/auth/lib/auth";

type Props = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  kbId: string;
  accountId: string;
  target: { file: KbFile; anchor: HTMLElement } | null;
  onDeleted: () => void;
};

export function KnowledgeDeletePopover({
  open,
  onOpenChange,
  kbId,
  accountId,
  target,
  onDeleted,
}: Props) {
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const deleteLock = useRef(false);
  const cancelDeleteRef = useRef<HTMLButtonElement>(null);

  const confirmDelete = async () => {
    if (deleteLock.current || !target) return;
    deleteLock.current = true;
    setDeleting(true);
    setDeleteError(null);
    try {
      await deleteKnowledgeDocumentRequest(accountId, kbId, target.file.id);
      if (localAccountId(useAuthStore.getState().user) !== accountId) return;
      onOpenChange(false);
      onDeleted();
    } catch (cause) {
      setDeleteError(cause instanceof Error ? cause.message : "删除失败，请重试。");
    } finally {
      deleteLock.current = false;
      setDeleting(false);
    }
  };

  return (
    <Popover
      open={open}
      onOpenChange={(next) => {
        if (!next && !deleteLock.current) onOpenChange(false);
      }}
    >
      <PopoverContent
        anchor={target?.anchor}
        align="start"
        className="w-72"
        aria-label="删除文档确认"
        initialFocus={cancelDeleteRef}
        finalFocus={() => (target?.anchor.isConnected ? target.anchor.querySelector("a") : false)}
      >
        <p className="text-sm font-medium">删除文档？</p>
        <p className="mt-2 break-words text-xs text-muted-foreground">
          确定删除「{target?.file.name}」？此操作无法撤销。
        </p>
        {deleteError && (
          <p role="alert" className="mt-2 text-xs text-destructive">
            {deleteError}
          </p>
        )}
        <div className="mt-4 flex justify-end gap-2">
          <Button
            size="sm"
            variant="outline"
            ref={cancelDeleteRef}
            disabled={deleting}
            onClick={() => onOpenChange(false)}
          >
            取消
          </Button>
          <Button
            size="sm"
            variant="destructive"
            disabled={deleting}
            onClick={() => void confirmDelete()}
          >
            {deleting && <Loader2 className="size-3 animate-spin" />}
            {deleting ? "删除中…" : "确认删除"}
          </Button>
        </div>
      </PopoverContent>
    </Popover>
  );
}
