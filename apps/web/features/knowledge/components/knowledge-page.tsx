"use client";

import { useParams } from "@tanstack/react-router";
import { Link } from "@tanstack/react-router";
import { useState, useRef, type ChangeEvent } from "react";
import { ArrowLeft, BookOpen, Eye, FileText, Plus, Upload, UploadCloud, Users } from "lucide-react";
import { cn } from "cn";
import { Button, buttonVariants } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { PdfPreview } from "@/features/knowledge/components/pdf-preview";
import { BlockNoteEditor } from "@/features/editor/components/blocknote-editor";
import { appendUploadedFile, getKbFiles } from "@/features/knowledge/utils/kb-upload-store";
import {
  FILE_TYPE_META,
  KNOWLEDGE_BASES,
  type KbFile,
  type KnowledgeBase,
} from "@/features/knowledge/constants/knowledge-data";

/** 文件大小格式化：< 1MB 显示 KB，否则显示 MB */
function formatSize(bytes: number): string {
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

/** 知识库列表页（/knowledge） */
export function KnowledgePage() {
  const [bases, setBases] = useState<KnowledgeBase[]>(() => KNOWLEDGE_BASES);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [createErr, setCreateErr] = useState<string | null>(null);

  const createKb = () => {
    const trimmed = name.trim();
    if (!trimmed) {
      setCreateErr("请输入知识库名称");
      return;
    }
    setBases((prev) => [
      {
        id: `kb-${Date.now()}`,
        name: trimmed,
        description: description.trim() || "暂无描述",
        owner: "我",
        files: [],
      },
      ...prev,
    ]);
    setDialogOpen(false);
    setName("");
    setDescription("");
    setCreateErr(null);
  };

  return (
    <div className="flex w-full flex-1 flex-col gap-6 px-6 py-8 md:px-10">
      <header className="flex items-start justify-between gap-4">
        <div className="flex flex-col gap-1">
          <h1 className="text-2xl font-semibold tracking-tight">知识库</h1>
          <p className="text-muted-foreground text-sm">
            建立自己的知识库，对话中使用 @ 选择知识库作为回答上下文
          </p>
        </div>
        <Button onClick={() => setDialogOpen(true)}>
          <Plus className="size-4" />
          新建知识库
        </Button>
      </header>

      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>新建知识库</DialogTitle>
            <DialogDescription>输入知识库名称与描述，创建后即可上传文档</DialogDescription>
          </DialogHeader>
          <div className="flex flex-col gap-3">
            <Input
              placeholder="知识库名称（必填）"
              value={name}
              onChange={(e) => setName(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") createKb();
              }}
              style={{ borderRadius: 4 }}
            />
            <Textarea
              placeholder="描述（可选）"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={3}
              style={{ borderRadius: 4 }}
            />
            {createErr && (
              <p className="text-red-500 text-xs" role="alert">
                {createErr}
              </p>
            )}
          </div>
          <DialogFooter>
            <DialogClose render={<Button variant="ghost">取消</Button>} />
            <Button onClick={createKb}>创建</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <ul className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {bases.map((kb) => (
          <li key={kb.id} className="flex flex-col gap-3 rounded-xl border bg-card p-4">
            <div className="flex items-start justify-between gap-2">
              <div className="bg-muted text-muted-foreground flex size-9 items-center justify-center rounded-lg">
                <BookOpen className="size-4" />
              </div>
              <span className="bg-muted text-muted-foreground rounded-full px-2 py-0.5 text-xs">
                {kb.owner}
              </span>
            </div>
            <div className="flex flex-col gap-0.5">
              <span className="text-sm font-medium">{kb.name}</span>
              <span className="text-muted-foreground text-xs">{kb.description}</span>
            </div>
            <div className="text-muted-foreground flex items-center gap-3 text-xs">
              <span className="flex items-center gap-1">
                <FileText className="size-3.5" />
                {kb.files.length} 个文件
              </span>
              <span>更新于 {kb.files[0]?.updatedAt ?? "—"}</span>
            </div>
            <Link
              to="/knowledge/$kbId"
              params={{ kbId: kb.id }}
              className={buttonVariants({
                variant: "outline",
                size: "sm",
                className: "mt-auto w-fit",
              })}
            >
              <Users className="size-3.5" />
              打开知识库
            </Link>
          </li>
        ))}
      </ul>

      <p className="text-muted-foreground text-xs">* 知识库列表与新建为 UI 骨架，功能待接入</p>
    </div>
  );
}

/** 知识库详情页（/knowledge/$kbId）：文件列表，支持上传 md / pdf */
export function KnowledgeBaseDetailPage() {
  const { kbId } = useParams({ from: "/_app/knowledge/$kbId/" });
  const kb = KNOWLEDGE_BASES.find((k) => k.id === kbId);
  const [files, setFiles] = useState<KbFile[]>(() => getKbFiles(kbId));
  const [uploadMsg, setUploadMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [dialogErr, setDialogErr] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);
  const inputRef = useRef<HTMLInputElement | null>(null);

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
      appendUploadedFile(kb.id, entry);
      setFiles((prev) => [entry, ...prev]);
      setUploadMsg({ ok: true, text: `已上传 ${file.name}` });
      setDialogOpen(false);
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
        <Button onClick={() => setDialogOpen(true)}>
          <Upload className="size-4" />
          上传文件
        </Button>
      </header>

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
        <ul className="flex flex-col gap-2">
          {files.map((file) => {
            const meta = FILE_TYPE_META[file.type];
            const Icon = meta.icon;
            return (
              <li
                key={file.id}
                className="flex items-center justify-between gap-4 rounded-xl border bg-card px-4 py-3"
              >
                <div className="flex min-w-0 items-center gap-3">
                  <div className="bg-muted text-muted-foreground flex size-9 shrink-0 items-center justify-center rounded-lg">
                    <Icon className="size-4" />
                  </div>
                  <div className="flex min-w-0 flex-col gap-0.5">
                    <span className="truncate text-sm font-medium">{file.name}</span>
                    <span className="text-muted-foreground flex items-center gap-2 text-xs">
                      <span className="bg-muted text-muted-foreground rounded px-1.5 py-0.5 text-[10px]">
                        {meta.label}
                      </span>
                      <span>{file.size}</span>
                      <span>{file.uploader} 上传</span>
                      <span>更新于 {file.updatedAt}</span>
                    </span>
                  </div>
                </div>
                <div className="flex shrink-0 items-center gap-2">
                  <Link
                    to="/knowledge/$kbId/files/$fileId"
                    params={{ kbId: kb.id, fileId: file.id }}
                    className={buttonVariants({ variant: "ghost", size: "sm" })}
                  >
                    <Eye className="size-4" />
                    查看
                  </Link>
                </div>
              </li>
            );
          })}
          {files.length === 0 && (
            <li className="text-muted-foreground rounded-xl border border-dashed p-6 text-center text-sm">
              暂无文件，点击右上角上传
            </li>
          )}
        </ul>
      </section>

      <p className="text-muted-foreground text-xs">
        * 仅支持 Markdown 与 PDF 格式，单次选择一个文件；上传后即可在线预览
      </p>
    </div>
  );
}

/** 文档查看页（/knowledge/$kbId/files/$fileId）：源文件只读 + 解析结果富文本可编辑 */
export function KnowledgeFilePage() {
  const { kbId, fileId } = useParams({ from: "/_app/knowledge/$kbId/files/$fileId" });

  const kb = KNOWLEDGE_BASES.find((k) => k.id === kbId);
  const file = getKbFiles(kbId).find((f) => f.id === fileId);

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

      <header className="flex flex-col gap-2">
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
          <span>{file.uploader} 上传</span>
          <span>更新于 {file.updatedAt}</span>
        </p>
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
              <BlockNoteEditor markdown={file.content} editable={false} className="px-4 py-4" />
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
                <BlockNoteEditor markdown={file.content ?? ""} className="px-4 py-4" />
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
