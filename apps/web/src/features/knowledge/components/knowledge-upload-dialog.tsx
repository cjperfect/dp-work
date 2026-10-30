import { useRef, useState, type ChangeEvent } from "react";
import { Loader2, UploadCloud } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { uploadKnowledgeDocumentRequest } from "@/apis/knowledge";
import { useAuthStore } from "@/stores/auth";
import { localAccountId } from "@/features/auth/lib/auth";
import { cn } from "cn";

type Props = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  kbId: string;
  accountId: string;
  onUploaded: (fileName: string) => void;
};

export function KnowledgeUploadDialog({ open, onOpenChange, kbId, accountId, onUploaded }: Props) {
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [dragging, setDragging] = useState(false);
  const [dialogErr, setDialogErr] = useState<string | null>(null);
  const uploadLock = useRef(false);
  const inputRef = useRef<HTMLInputElement | null>(null);

  const handleFile = async (file: File) => {
    if (uploadLock.current) return;
    uploadLock.current = true;
    setUploading(true);
    setUploadProgress(0);
    setDialogErr(null);
    try {
      await uploadKnowledgeDocumentRequest(accountId, kbId, file, setUploadProgress);
      if (localAccountId(useAuthStore.getState().user) !== accountId) return;
      onUploaded(file.name);
      onOpenChange(false);
    } catch (cause) {
      setDialogErr(cause instanceof Error ? cause.message : "上传失败，请重试。");
    } finally {
      uploadLock.current = false;
      setUploading(false);
    }
  };

  const onPickFile = (e: ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (file) void handleFile(file);
  };

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!uploadLock.current) onOpenChange(next);
      }}
    >
      <DialogContent showCloseButton={!uploading}>
        <DialogHeader>
          <DialogTitle>上传文件</DialogTitle>
          <DialogDescription>
            支持 TXT、Markdown、PDF、Word，单次选择一个文件，最大 20 MB。
          </DialogDescription>
        </DialogHeader>
        <div
          role="button"
          tabIndex={uploading ? -1 : 0}
          aria-busy={uploading}
          aria-disabled={uploading}
          aria-label="选择上传文件"
          className={cn(
            "flex cursor-pointer flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed px-8 py-10 text-center transition-colors outline-none focus-visible:ring-2 focus-visible:ring-ring",
            dragging
              ? "border-primary bg-primary/5"
              : "border-muted-foreground/25 hover:bg-muted/50",
          )}
          onClick={() => {
            if (!uploading) inputRef.current?.click();
          }}
          onKeyDown={(e) => {
            if (!uploading && (e.key === "Enter" || e.key === " ")) {
              e.preventDefault();
              inputRef.current?.click();
            }
          }}
          onDragOver={(e) => {
            e.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDragging(false);
            const f = e.dataTransfer.files?.[0];
            if (f) void handleFile(f);
          }}
        >
          {uploading ? (
            <Loader2 className="size-8 animate-spin text-muted-foreground" />
          ) : (
            <UploadCloud className="size-8 text-muted-foreground" />
          )}
          <p role="status" className="text-sm font-medium">
            {uploading ? `上传中… ${uploadProgress}%` : "点击选择文件，或将文件拖拽到此处"}
          </p>
          <p className="text-xs text-muted-foreground">
            支持 TXT / Markdown / PDF / Word，最大 20 MB
          </p>
        </div>
        <input
          ref={inputRef}
          type="file"
          disabled={uploading}
          accept=".txt,.md,.markdown,.pdf,.doc,.docx"
          className="hidden"
          onChange={onPickFile}
        />
        {dialogErr && (
          <p className="text-red-500 text-xs" role="alert">
            {dialogErr}
          </p>
        )}
      </DialogContent>
    </Dialog>
  );
}
