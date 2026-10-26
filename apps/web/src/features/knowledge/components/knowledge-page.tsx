import { toast } from "sonner";
import { ParsedDocumentEditor } from "./parsed-document-editor";
import { localAccountId } from "@/features/auth/lib/auth";
import { useParams } from "@tanstack/react-router";
import { Link } from "@tanstack/react-router";
import { useState, useRef, useEffect, useCallback, type ChangeEvent } from "react";
import {
  ArrowLeft,
  ChevronRight,
  Info,
  FilePlus2,
  FileText,
  ScanText,
  Network,
  Trash2,
  Loader2,
  Upload,
  UploadCloud,
} from "lucide-react";
import { cn } from "cn";
import { Button, buttonVariants } from "@/components/ui/button";
import {
  ContextMenu,
  ContextMenuTrigger,
  ContextMenuContent,
  ContextMenuItem,
} from "@/components/ui/context-menu";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Popover, PopoverContent } from "@/components/ui/popover";
import {
  deleteKnowledgeDocument,
  saveKnowledgeDocument,
  uploadKnowledgeDocument,
} from "@/stores/knowledge";
import { Input } from "@/components/ui/input";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useKnowledgeDocuments } from "@/features/knowledge/hooks/use-knowledge-documents";
import { useKnowledgeBases } from "@/features/knowledge/hooks/use-knowledge-bases";
import { useAuthStore } from "@/stores/auth";
import { useDocumentPdf } from "@/features/knowledge/hooks/use-document-pdf";
import { useDocumentParsing, parseStatusLabel } from "../hooks/use-document-parsing";
import { ParseDocumentButton } from "./parse-document-button";
import { EditableSourceEditor } from "./editable-source-editor";
import { PdfPreview } from "@/features/knowledge/components/pdf-preview";
import { LazyBlockNoteEditor as BlockNoteEditor } from "@/components/editor/lazy-blocknote-editor";
import { getKbFiles, removeUploadedFile } from "@/stores/knowledge-upload";
import {
  FILE_TYPE_META,
  KNOWLEDGE_BASES,
  type KbFile,
} from "@/features/knowledge/constants/knowledge-data";

export { KnowledgePage } from "./knowledge-list-page";

/** 文档解析状态标签配色：未解析（中性灰）、已解析（绿）、已向量化（蓝） */
const PARSE_STATUS_TONE: Record<string, string> = {
  已解析: "bg-emerald-500/10 text-emerald-600",
  已向量化: "bg-sky-500/10 text-sky-600",
};

/** 知识库详情页（/knowledge/$kbId）：文件列表，支持上传 md / pdf */
export function KnowledgeBaseDetailPage() {
  const { kbId } = useParams({ from: "/_app/knowledge/$kbId/" });
  const { bases, loading, error, reload } = useKnowledgeBases();
  const documents = useKnowledgeDocuments(kbId);
  // 后端知识库/文档接口不可用或未接入时，降级为本地 mock + 本地上传数据，页面始终可看
  const kb = bases.find((k) => k.id === kbId) ?? KNOWLEDGE_BASES.find((k) => k.id === kbId);
  const backendUnavailable = Boolean(error || documents.error);
  const files = Array.from(
    new Map(
      [
        ...(backendUnavailable || documents.loading ? (kb?.files ?? []) : documents.files),
        ...getKbFiles(kbId),
      ].map((file) => [file.id, file]),
    ).values(),
  );
  const accountId = useAuthStore((state) => localAccountId(state.user));
  const [uploadMsg, setUploadMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const parsing = useDocumentParsing(kbId);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [dialogErr, setDialogErr] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const uploadLock = useRef(false);
  const [dragging, setDragging] = useState(false);
  const inputRef = useRef<HTMLInputElement | null>(null);
  const cards = useRef(new Map<string, HTMLLIElement>());
  const [deleteTarget, setDeleteTarget] = useState<{
    kbId: string;
    file: KbFile;
    anchor: HTMLElement;
  } | null>(null);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const deleteLock = useRef(false);
  const cancelDeleteRef = useRef<HTMLButtonElement>(null);

  async function confirmDelete() {
    if (
      !deleteOpen ||
      !deleteTarget ||
      !accountId ||
      deleteLock.current ||
      deleteTarget.kbId !== kbId
    )
      return;
    const target = deleteTarget;
    deleteLock.current = true;
    setDeleting(true);
    setDeleteError(null);
    try {
      if (target.file.source === "editor" || target.file.storage === "server")
        await deleteKnowledgeDocument(accountId, kbId, target.file.id);
      else removeUploadedFile(kbId, target.file.id, accountId);
      if (localAccountId(useAuthStore.getState().user) !== accountId) return;
      setDeleteOpen(false);
      documents.reload();
    } catch (cause) {
      setDeleteError(cause instanceof Error ? cause.message : "删除失败，请重试。");
    } finally {
      deleteLock.current = false;
      setDeleting(false);
    }
  }

  // 仅当本地也无对应知识库时才阻断：加载中显示加载态，其余按不存在处理
  if ((loading || error || documents.loading || documents.error) && !kb)
    return (
      <KnowledgeLoadState
        error={error ?? documents.error}
        reload={() => {
          reload();
          documents.reload();
        }}
      />
    );

  if (!kb) {
    return (
      <div className="text-muted-foreground flex flex-1 flex-col items-center justify-center gap-3">
        知识库不存在
        <Link to="/knowledge" className={buttonVariants({ variant: "outline", size: "sm" })}>
          返回知识库列表
        </Link>
      </div>
    );
  }

  /** 上传源文件，后端确认成功后更新列表。 */
  const handleFile = async (file: File) => {
    if (uploadLock.current || !accountId) return;
    uploadLock.current = true;
    setUploading(true);
    setUploadProgress(0);
    setDialogErr(null);
    try {
      await uploadKnowledgeDocument(accountId, kb.id, file, setUploadProgress);
      if (localAccountId(useAuthStore.getState().user) !== accountId) return;
      setUploadMsg({ ok: true, text: `已上传 ${file.name}` });
      setDialogOpen(false);
      documents.reload();
    } catch (cause) {
      setDialogErr(cause instanceof Error ? cause.message : "上传失败，请重试。");
    } finally {
      uploadLock.current = false;
      setUploading(false);
    }
  };

  const onPickFile = (e: ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    e.target.value = ""; // 允许重复选择同一文件
    if (file) void handleFile(file);
  };

  return (
    <div className="flex w-full flex-1 flex-col gap-6 px-6 py-8 md:px-10">
      <div className="flex items-center gap-2">
        <Link to="/knowledge" className={buttonVariants({ variant: "ghost", size: "sm" })}>
          <ArrowLeft className="size-4" />
          返回知识库列表
        </Link>
      </div>

      <header className="flex items-start justify-between gap-4">
        <div className="flex flex-col gap-1">
          <div className="flex items-center gap-2">
            <h1 className="text-2xl font-semibold tracking-tight">{kb.name}</h1>
            <span className="bg-muted text-muted-foreground rounded-full px-2 py-0.5 text-xs">
              {kb.owner}
            </span>
          </div>
          <p className="text-muted-foreground text-sm">{kb.description}</p>
        </div>
        <div className="flex shrink-0 flex-wrap items-center gap-2">
          <Button variant="outline" disabled={uploading} onClick={() => setDialogOpen(true)}>
            <Upload className="size-4" />
            上传文件
          </Button>
          <Button
            nativeButton={false}
            render={<Link to="/knowledge/$kbId/new" params={{ kbId: kb.id }} />}
          >
            <FilePlus2 className="size-4" />
            新建文档
          </Button>
        </div>
      </header>

      {backendUnavailable && (
        <p className="text-amber-600 text-xs" role="status">
          后端知识库服务暂不可用，当前展示本地预览数据
        </p>
      )}

      {uploadMsg && (
        <p
          className={`text-xs ${uploadMsg.ok ? "text-emerald-600" : "text-red-500"}`}
          role="status"
        >
          {uploadMsg.text}
        </p>
      )}

      <Dialog
        open={dialogOpen}
        onOpenChange={(open) => {
          if (!uploadLock.current) setDialogOpen(open);
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

      <aside
        aria-label="知识库使用指南"
        className="rounded-xl border border-sky-200 bg-sky-50/70 px-5 py-4 dark:border-sky-900 dark:bg-sky-950/30"
      >
        <div className="mb-3 flex items-center gap-2 text-sm font-semibold text-sky-950 dark:text-sky-100">
          <Info className="size-4 text-sky-600 dark:text-sky-400" />
          知识库使用步骤
        </div>
        <ol className="flex flex-wrap items-center gap-x-3 gap-y-3">
          {["上传文件 / 新建文档", "解析文档", "向量化", "在 Agent 中关联此知识库"].map(
            (step, index) => (
              <li key={step} className="flex items-center gap-3">
                {index > 0 && <ChevronRight aria-hidden="true" className="size-4 text-sky-400" />}
                <span className="flex items-center gap-2 text-sm font-medium text-sky-950 dark:text-sky-100">
                  <span
                    aria-hidden="true"
                    className="flex size-5 shrink-0 items-center justify-center rounded-full bg-sky-700 text-[11px] font-semibold text-white"
                  >
                    {index + 1}
                  </span>
                  {step}
                </span>
              </li>
            ),
          )}
        </ol>
        <p className="mt-3 text-xs leading-6 text-sky-800 dark:text-sky-200">
          完成后即可在 Agent 中使用。点击文档可查看或编辑，右键可解析、向量化或删除。
        </p>
        <p className="text-xs leading-6 text-sky-700/80 dark:text-sky-300/80">
          上传支持 TXT、Markdown、PDF、Word；目前支持 TXT、Markdown、PDF、DOCX 解析，旧版 DOC
          请先另存为 DOCX。在线文档修改后自动保存。
        </p>
      </aside>

      <section>
        <h2 className="mb-3 flex items-center gap-2 text-sm font-medium">
          <FileText className="text-muted-foreground size-4" />
          全部文件
          <span className="text-muted-foreground/60 text-xs">{files.length} 个</span>
        </h2>
        <ul className="grid grid-cols-[repeat(auto-fill,minmax(140px,1fr))] gap-x-5 gap-y-4">
          {files.map((file) => {
            const meta = FILE_TYPE_META[file.type];
            const extension = file.type === "md" ? "MD" : file.type.replace(/x$/, "").toUpperCase();
            const date = new Date(file.updatedAt);
            const displayDate = Number.isNaN(date.getTime())
              ? file.updatedAt
              : `${date.getMonth() + 1}/${date.getDate()}`;
            return (
              <ContextMenu key={file.id}>
                <ContextMenuTrigger
                  render={
                    <li
                      ref={(node) => {
                        if (node) cards.current.set(file.id, node);
                        else cards.current.delete(file.id);
                      }}
                      className="min-w-0 rounded-2xl data-[popup-open]:bg-muted/60"
                    />
                  }
                >
                  <Link
                    to="/knowledge/$kbId/files/$fileId"
                    params={{ kbId: kb.id, fileId: file.id }}
                    title={file.name}
                    className="group relative flex h-full min-w-0 flex-col items-center rounded-2xl px-3 pb-3 pt-9 text-center outline-none transition-colors hover:bg-muted/60 focus-visible:bg-muted/60 focus-visible:ring-2 focus-visible:ring-ring"
                  >
                    <span
                      title={file.parseError ?? parseStatusLabel(file)}
                      className={`absolute right-2 top-2 rounded-md px-1.5 py-0.5 text-[10px] font-medium ${
                        PARSE_STATUS_TONE[parseStatusLabel(file)] ??
                        "bg-muted text-muted-foreground"
                      }`}
                    >
                      {parseStatusLabel(file)}
                    </span>
                    {(file.parseStatus === "queued" || file.parseStatus === "parsing") && (
                      <span className="absolute left-2 top-2 text-[10px] text-muted-foreground">
                        解析中…
                      </span>
                    )}
                    <div
                      aria-hidden="true"
                      className={`mb-3 flex size-14 shrink-0 items-center justify-center rounded-2xl ${meta.badge}`}
                    >
                      <span className="flex h-8 min-w-7 items-center justify-center rounded-[5px] border-[1.5px] border-current px-1 text-[9px] font-semibold tracking-tight">
                        {extension}
                      </span>
                    </div>
                    <span className="line-clamp-2 min-h-10 w-full break-all text-xs font-medium leading-5">
                      {file.name}
                    </span>
                    <span className="mt-1 flex max-w-full flex-wrap items-center justify-center gap-x-1 text-[10px] leading-4 text-muted-foreground">
                      <span className={cn(meta.badge, "bg-transparent")}>{extension}</span>
                      <span aria-hidden="true">·</span>
                      <span>{file.size}</span>
                      <time dateTime={file.updatedAt} className="ml-0.5">
                        {displayDate}
                      </time>
                    </span>
                  </Link>
                </ContextMenuTrigger>
                <ContextMenuContent aria-label={`${file.name}的操作`}>
                  <ContextMenuItem
                    disabled={
                      parsing.submitting ||
                      file.parseStatus === "queued" ||
                      file.parseStatus === "parsing" ||
                      file.parseStatus === "parsed"
                    }
                    onClick={() => void parsing.start(file)}
                  >
                    <ScanText />
                    解析文档
                  </ContextMenuItem>
                  <ContextMenuItem
                    disabled={file.parseStatus !== "parsed" || !file.parsedContent?.trim()}
                    onClick={() => toast.info("向量化服务尚未接入，请先在解析后文档中检查内容。")}
                  >
                    <Network />
                    向量化
                  </ContextMenuItem>
                  <ContextMenuItem
                    className="text-destructive data-[highlighted]:bg-destructive/10 data-[highlighted]:text-destructive [&_svg]:text-destructive"
                    onClick={() => {
                      const anchor = cards.current.get(file.id);
                      if (anchor) {
                        setDeleteError(null);
                        setDeleteTarget({ kbId, file, anchor });
                        setDeleteOpen(true);
                      }
                    }}
                  >
                    <Trash2 />
                    删除
                  </ContextMenuItem>
                </ContextMenuContent>
              </ContextMenu>
            );
          })}
          {files.length === 0 && (
            <li className="text-muted-foreground col-span-full rounded-xl border border-dashed p-6 text-center text-sm">
              暂无文档，可以新建文档或上传文件
            </li>
          )}
        </ul>
      </section>

      <Popover
        open={deleteOpen && deleteTarget?.kbId === kbId}
        onOpenChange={(open) => {
          if (!open && !deleteLock.current) setDeleteOpen(false);
        }}
      >
        <PopoverContent
          anchor={deleteTarget?.anchor}
          align="start"
          className="w-72"
          aria-label="删除文档确认"
          initialFocus={cancelDeleteRef}
          finalFocus={() =>
            deleteTarget?.anchor.isConnected ? deleteTarget.anchor.querySelector("a") : false
          }
        >
          <p className="text-sm font-medium">删除文档？</p>
          <p className="mt-2 break-words text-xs text-muted-foreground">
            确定删除「{deleteTarget?.file.name}」？此操作无法撤销。
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
              onClick={() => setDeleteOpen(false)}
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
    </div>
  );
}

/** 文档查看页：分别展示源文档和处理后的文档。 */
export function KnowledgeFilePage() {
  const { kbId, fileId } = useParams({ from: "/_app/knowledge/$kbId/files/$fileId" });

  const { bases, loading, error, reload } = useKnowledgeBases();
  const kb = bases.find((k) => k.id === kbId);
  const documents = useKnowledgeDocuments(kbId);
  const file = [...documents.files, ...getKbFiles(kbId)].find((f) => f.id === fileId);
  const pdf = useDocumentPdf(kbId, file);
  const accountId = useAuthStore((state) => localAccountId(state.user));
  const [editingTitle, setEditingTitle] = useState(false);
  const [titleDraft, setTitleDraft] = useState("");
  const titleInput = useRef<HTMLInputElement>(null);
  const titleButton = useRef<HTMLButtonElement>(null);
  const cancelTitle = useRef(false);

  useEffect(() => {
    if (editingTitle) {
      titleInput.current?.focus();
      titleInput.current?.select();
    }
  }, [editingTitle]);

  const displayTitle = file?.name.replace(/\.md$/i, "").trim() || "未命名文档";

  async function finishTitle() {
    setEditingTitle(false);
    if (cancelTitle.current || !file) {
      cancelTitle.current = false;
      return;
    }
    const next = titleDraft.trim().replace(/\.md$/i, "").trim() || "未命名文档";
    if (next === displayTitle || !accountId) return;
    try {
      await saveKnowledgeDocument(accountId, kbId, {
        id: file.id,
        title: next,
        content: file.content ?? "",
        blocks: file.blocks,
        status: "published",
      });
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : "标题保存失败，请重试。");
    }
  }
  const [parsedSaveBlocked, setParsedSaveBlocked] = useState(false);
  const onParsedSaveStateChange = useCallback(
    (blocked: boolean) => setParsedSaveBlocked(blocked),
    [],
  );

  if (loading || error || documents.loading || documents.error)
    return (
      <KnowledgeLoadState
        error={error ?? documents.error}
        reload={() => {
          reload();
          documents.reload();
        }}
      />
    );

  if (!kb || !file) {
    return (
      <div className="text-muted-foreground flex flex-1 flex-col items-center justify-center gap-3">
        文档不存在
        <Link to="/knowledge" className={buttonVariants({ variant: "outline", size: "sm" })}>
          返回知识库列表
        </Link>
      </div>
    );
  }

  const meta = FILE_TYPE_META[file.type];
  const Icon = meta.icon;
  const isPdf = file.type === "pdf";

  return (
    <div className="flex h-full w-full flex-col gap-6 px-6 py-8 md:px-10">
      <div className="flex items-center gap-2">
        <Link
          to="/knowledge/$kbId"
          params={{ kbId: kb.id }}
          className={buttonVariants({ variant: "ghost", size: "sm" })}
        >
          <ArrowLeft className="size-4" />
          返回 {kb.name}
        </Link>
      </div>

      <header className="flex flex-wrap items-start justify-between gap-4">
        <div className="flex min-w-0 flex-col gap-2">
          <div className="flex items-center gap-2">
            <div className="bg-muted text-muted-foreground flex size-8 shrink-0 items-center justify-center rounded-lg">
              <Icon className="size-4" />
            </div>
            {file.source === "editor" ? (
              editingTitle ? (
                <Input
                  ref={titleInput}
                  aria-label="文档标题"
                  value={titleDraft}
                  onChange={(event) => setTitleDraft(event.target.value)}
                  onBlur={() => void finishTitle()}
                  onKeyDown={(event) => {
                    if (event.nativeEvent.isComposing) return;
                    if (event.key === "Enter" || event.key === "Escape") {
                      event.preventDefault();
                      cancelTitle.current = event.key === "Escape";
                      event.currentTarget.blur();
                    }
                  }}
                  placeholder="未命名文档"
                  className="h-8 max-w-md text-xl! font-semibold"
                />
              ) : (
                <button
                  ref={titleButton}
                  type="button"
                  aria-label={`修改文档标题：${displayTitle}`}
                  title="点击修改标题"
                  className="max-w-full truncate rounded-sm py-0.5 text-xl font-semibold tracking-tight outline-none hover:text-foreground/75 focus-visible:ring-2 focus-visible:ring-ring"
                  onClick={() => {
                    setTitleDraft(displayTitle);
                    setEditingTitle(true);
                  }}
                >
                  {displayTitle}
                </button>
              )
            ) : (
              <h1 className="truncate text-xl font-semibold tracking-tight">{file.name}</h1>
            )}
          </div>
          <p className="text-muted-foreground flex flex-wrap items-center gap-2 text-xs">
            <span className="bg-muted text-muted-foreground rounded px-1.5 py-0.5 text-[10px]">
              {meta.label}
            </span>
            <span>{file.size}</span>
            <span>
              {file.uploader} {file.source === "editor" ? "创建" : "上传"}
            </span>
            <span>更新于 {formatDateTime(file.updatedAt)}</span>
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <ParseDocumentButton baseId={kbId} file={file} />
          <Button
            disabled={
              file.parseStatus !== "parsed" || parsedSaveBlocked || !file.parsedContent?.trim()
            }
            title={
              parsedSaveBlocked ? "请等待解析文档保存完成" : "先解析并检查文档内容，再进行向量化"
            }
            onClick={() => toast.info("向量化服务尚未接入，解析文档已保存。")}
          >
            <Network className="size-4" />
            向量化
          </Button>
        </div>
      </header>

      <section className="flex min-h-0 flex-1 flex-col rounded-xl border bg-card">
        <Tabs defaultValue="source" className="flex min-h-0 flex-1 flex-col">
          <TabsList className="mx-4 mt-4 w-fit">
            <TabsTrigger value="source">源文档</TabsTrigger>
            <TabsTrigger value="rendered">解析后文档</TabsTrigger>
          </TabsList>
          <TabsContent value="source" className="min-h-0 flex-1 overflow-auto">
            {file.source === "editor" ? (
              accountId ? (
                <EditableSourceEditor accountId={accountId} baseId={kb.id} file={file} />
              ) : (
                <BlockNoteEditor
                  initialContent={file.blocks}
                  markdown={file.blocks ? undefined : file.content}
                  editable={false}
                  className="px-4 py-4"
                />
              )
            ) : isPdf ? (
              pdf.url ? (
                <PdfPreview url={pdf.url} />
              ) : (
                <div
                  role={pdf.error ? "alert" : "status"}
                  className="p-8 text-sm text-muted-foreground"
                >
                  {pdf.error ?? "正在读取 PDF…"}
                </div>
              )
            ) : file.content || file.blocks?.length ? (
              <BlockNoteEditor
                initialContent={file.blocks}
                markdown={file.blocks ? undefined : file.content}
                editable={false}
                className="px-4 py-4"
              />
            ) : (
              <div className="text-muted-foreground flex h-full min-h-64 flex-col items-center justify-center gap-2">
                <Icon className="size-8" />
                <p className="text-sm">该文件没有可查看的源文件内容</p>
              </div>
            )}
          </TabsContent>
          <TabsContent value="rendered" className="min-h-0 flex-1 overflow-auto">
            {file.parseStatus === "parsed" ? (
              <ParsedDocumentEditor
                key={file.id}
                baseId={kbId}
                file={file}
                onSaveStateChange={onParsedSaveStateChange}
              />
            ) : (
              <div className="flex h-full min-h-64 flex-col items-center justify-center gap-3 px-6 py-10 text-center">
                <span className="flex size-11 items-center justify-center rounded-xl bg-muted text-muted-foreground">
                  <ScanText className="size-5" />
                </span>
                <p className="text-sm font-medium">
                  {file.parseStatus === "queued" || file.parseStatus === "parsing"
                    ? "正在解析文档…"
                    : file.parseStatus === "failed"
                      ? "解析失败"
                      : "暂无解析后文档"}
                </p>
                <p className="max-w-sm text-xs leading-6 text-muted-foreground">
                  {file.parseError ??
                    "点击解析文档提取正文，TXT、Markdown 保留原有内容格式；图片与 OCR 暂不处理。"}
                </p>
              </div>
            )}
          </TabsContent>
        </Tabs>
      </section>
    </div>
  );
}

/** 将 ISO 时间格式化为本地可读时间（YYYY-MM-DD HH:mm）。 */
function formatDateTime(value?: string): string {
  if (!value) return "未知";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

function KnowledgeLoadState({ error, reload }: { error: string | null; reload: () => void }) {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-3 px-6 text-center">
      <p role={error ? "alert" : "status"} className="text-sm text-muted-foreground">
        {error || "正在读取知识库…"}
      </p>
      {error && (
        <Button variant="outline" size="sm" onClick={reload}>
          重新加载
        </Button>
      )}
    </div>
  );
}
