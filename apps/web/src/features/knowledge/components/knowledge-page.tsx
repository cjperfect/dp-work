import { localAccountId } from "@/features/auth/lib/auth";
import { useParams } from "@tanstack/react-router";
import { Link } from "@tanstack/react-router";
import { useState, useRef, type ChangeEvent } from "react";
import { ArrowLeft, FilePlus2, FileText, Pencil, Upload, UploadCloud } from "lucide-react";
import { cn } from "cn";
import { Button, buttonVariants } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useKnowledgeDocuments } from "@/features/knowledge/hooks/use-knowledge-documents";
import { useKnowledgeBases } from "@/features/knowledge/hooks/use-knowledge-bases";
import { useAuthStore } from "@/stores/auth";
import { PdfPreview } from "@/features/knowledge/components/pdf-preview";
import { LazyBlockNoteEditor as BlockNoteEditor } from "@/components/editor/lazy-blocknote-editor";
import { appendUploadedFile, getKbFiles } from "@/stores/knowledge-upload";
import {
  FILE_TYPE_META,
  KNOWLEDGE_BASES,
  type KbFile,
} from "@/features/knowledge/constants/knowledge-data";

/** 文件大小格式化：< 1MB 显示 KB，否则显示 MB */
function formatSize(bytes: number): string {
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export { KnowledgePage } from "./knowledge-list-page";

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
  const [dialogOpen, setDialogOpen] = useState(false);
  const [dialogErr, setDialogErr] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);
  const inputRef = useRef<HTMLInputElement | null>(null);

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

  /** 处理单个文件：仅允许 md / pdf，成功后写入存储并关闭弹窗 */
  const handleFile = (file: File) => {
    const ext = file.name.split(".").pop()?.toLowerCase();
    if (ext !== "md" && ext !== "pdf") {
      setDialogErr(`仅支持 Markdown 与 PDF，已忽略「${file.name}」`);
      return;
    }
    setDialogErr(null);
    const now = new Date().toISOString().slice(0, 10);
    const id = `f-${Date.now()}`;
    const base = {
      id,
      name: file.name,
      size: formatSize(file.size),
      uploader: "我",
      updatedAt: now,
    };
    const done = (entry: KbFile) => {
      if (!accountId || localAccountId(useAuthStore.getState().user) !== accountId) return;
      try {
        appendUploadedFile(kb.id, entry, accountId);
        setUploadMsg({ ok: true, text: `已上传 ${file.name}` });
        setDialogOpen(false);
      } catch {
        setDialogErr("本地保存失败，请检查浏览器存储空间后重试。");
      }
    };
    if (ext === "md") {
      file
        .text()
        .then((content) => done({ ...base, type: "md", content }))
        .catch(() => setDialogErr(`读取 ${file.name} 失败，请重试`));
    } else {
      const reader = new FileReader();
      reader.onload = () => done({ ...base, type: "pdf", pdfUrl: reader.result as string });
      reader.onerror = () => setDialogErr(`读取 ${file.name} 失败，请重试`);
      reader.readAsDataURL(file);
    }
  };

  const onPickFile = (e: ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    e.target.value = ""; // 允许重复选择同一文件
    if (file) handleFile(file);
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
          <Button variant="outline" onClick={() => setDialogOpen(true)}>
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

      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>上传文件</DialogTitle>
            <DialogDescription>仅支持 Markdown 与 PDF，单次选择一个文件</DialogDescription>
          </DialogHeader>
          <div
            role="button"
            tabIndex={0}
            aria-label="选择上传文件"
            className={cn(
              "flex cursor-pointer flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed px-8 py-10 text-center transition-colors outline-none focus-visible:ring-2 focus-visible:ring-ring",
              dragging
                ? "border-primary bg-primary/5"
                : "border-muted-foreground/25 hover:bg-muted/50",
            )}
            onClick={() => inputRef.current?.click()}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") inputRef.current?.click();
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
              if (f) handleFile(f);
            }}
          >
            <UploadCloud className="text-muted-foreground size-8" />
            <p className="text-sm font-medium">点击选择文件，或将文件拖拽到此处</p>
            <p className="text-muted-foreground text-xs">支持 .md / .pdf</p>
          </div>
          <input
            ref={inputRef}
            type="file"
            accept=".md,.pdf"
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
            const savedToServer = file.id.startsWith("doc-");
            const date = new Date(file.updatedAt);
            const displayDate = Number.isNaN(date.getTime())
              ? file.updatedAt
              : `${date.getMonth() + 1}/${date.getDate()}`;
            return (
              <li key={file.id} className="min-w-0">
                <Link
                  to={
                    file.status === "draft" && file.source === "editor"
                      ? "/knowledge/$kbId/edit/$fileId"
                      : "/knowledge/$kbId/files/$fileId"
                  }
                  params={{ kbId: kb.id, fileId: file.id }}
                  title={file.name}
                  className="group relative flex h-full min-w-0 flex-col items-center rounded-2xl px-3 pb-3 pt-4 text-center outline-none transition-colors hover:bg-muted/60 focus-visible:bg-muted/60 focus-visible:ring-2 focus-visible:ring-ring"
                >
                  {file.status === "draft" ? (
                    <span className="absolute right-2 top-2 rounded-md bg-amber-500/10 px-1.5 py-0.5 text-[10px] text-amber-700">
                      草稿
                    </span>
                  ) : (
                    <span
                      title={savedToServer ? "本地演示文档" : "此浏览器中的文件"}
                      className={cn(
                        "absolute right-3 top-3 size-1.5 rounded-full",
                        savedToServer ? "bg-emerald-500/70" : "bg-muted-foreground/30",
                      )}
                    >
                      <span className="sr-only">
                        {savedToServer ? "本地演示文档" : "此浏览器中的文件"}
                      </span>
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
              </li>
            );
          })}
          {files.length === 0 && (
            <li className="text-muted-foreground col-span-full rounded-xl border border-dashed p-6 text-center text-sm">
              暂无文档，可以新建文档或上传文件
            </li>
          )}
        </ul>
      </section>

      <p className="text-muted-foreground text-xs">
        上传支持 Markdown 与 PDF；在线文档可保存为草稿，或保存后阅读。
      </p>
    </div>
  );
}

/** 文档查看页（/knowledge/$kbId/files/$fileId）：源文件只读 + 解析结果富文本可编辑 */
export function KnowledgeFilePage() {
  const { kbId, fileId } = useParams({ from: "/_app/knowledge/$kbId/files/$fileId" });

  const { bases, loading, error, reload } = useKnowledgeBases();
  const kb = bases.find((k) => k.id === kbId);
  const documents = useKnowledgeDocuments(kbId);
  const file = [...documents.files, ...getKbFiles(kbId)].find((f) => f.id === fileId);

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
  const isPdf = file.type === "pdf" && !!file.pdfUrl;

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
            <h1 className="truncate text-xl font-semibold tracking-tight">{file.name}</h1>
          </div>
          <p className="text-muted-foreground flex flex-wrap items-center gap-2 text-xs">
            <span className="bg-muted text-muted-foreground rounded px-1.5 py-0.5 text-[10px]">
              {meta.label}
            </span>
            <span>{file.size}</span>
            <span>
              {file.uploader} {file.source === "editor" ? "创建" : "上传"}
            </span>
            <span>更新于 {file.updatedAt}</span>
          </p>
        </div>
        {file.source === "editor" && (
          <Button
            variant="outline"
            nativeButton={false}
            render={
              <Link to="/knowledge/$kbId/edit/$fileId" params={{ kbId: kb.id, fileId: file.id }} />
            }
          >
            <Pencil className="size-4" />
            编辑文档
          </Button>
        )}
      </header>

      <section className="flex min-h-0 flex-1 flex-col rounded-xl border bg-card">
        <Tabs defaultValue="source" className="flex min-h-0 flex-1 flex-col">
          <TabsList className="mx-4 mt-4 w-fit">
            <TabsTrigger value="source">源文件</TabsTrigger>
            <TabsTrigger value="rendered">解析结果</TabsTrigger>
          </TabsList>
          <TabsContent value="source" className="min-h-0 flex-1 overflow-auto">
            {isPdf ? (
              <PdfPreview url={file.pdfUrl!} />
            ) : file.content ? (
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
            {file.type === "md" ? (
              <div className="min-h-0 flex-1">
                <BlockNoteEditor
                  initialContent={file.blocks}
                  markdown={file.blocks ? undefined : (file.content ?? "")}
                  editable={file.source !== "editor" && !file.id.startsWith("doc-")}
                  className="px-4 py-4"
                />
              </div>
            ) : (
              <div className="text-muted-foreground flex h-full min-h-64 flex-col items-center justify-center gap-2">
                <Icon className="size-8" />
                <p className="text-sm">该 PDF 暂无解析结果，待接入文档解析后展示 Markdown 内容</p>
              </div>
            )}
          </TabsContent>
        </Tabs>
      </section>
    </div>
  );
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
