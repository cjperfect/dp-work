import type { KbFile } from "@/interfaces/knowledge";
import { localAccountId } from "@/features/auth/lib/auth";
import { useParams } from "@tanstack/react-router";
import { Link } from "@tanstack/react-router";
import { useState, useRef } from "react";
import {
  ArrowLeft,
  ChevronRight,
  Info,
  FilePlus2,
  FileText,
  ScanText,
  Network,
  Trash2,
  Upload,
} from "lucide-react";
import { cn } from "cn";
import { Button, buttonVariants } from "@/components/ui/button";
import {
  ContextMenu,
  ContextMenuTrigger,
  ContextMenuContent,
  ContextMenuItem,
} from "@/components/ui/context-menu";

import { useKnowledgeDocuments } from "@/features/knowledge/hooks/use-knowledge-documents";
import { useKnowledgeBases } from "@/features/knowledge/hooks/use-knowledge-bases";
import { useAuthStore } from "@/stores/auth";

import {
  useDocumentParsing,
  useDocumentVectorization,
  parseStatusLabel,
} from "../hooks/use-document-parsing";

import { FILE_TYPE_META } from "@/constants/knowledge";
import { KnowledgeUploadDialog } from "./knowledge-upload-dialog";
import { KnowledgeDeletePopover } from "./knowledge-delete-popover";

export { KnowledgePage } from "./knowledge-list-page";
export { KnowledgeFilePage } from "./knowledge-file-page";

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
  const kb = bases.find((base) => base.id === kbId);
  const files = documents.files;
  const accountId = useAuthStore((state) => localAccountId(state.user));
  const [uploadMsg, setUploadMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const parsing = useDocumentParsing(kbId);
  const vectorization = useDocumentVectorization(kbId);
  const [dialogOpen, setDialogOpen] = useState(false);
  const cards = useRef(new Map<string, HTMLLIElement>());
  const [deleteTarget, setDeleteTarget] = useState<{
    kbId: string;
    file: KbFile;
    anchor: HTMLElement;
  } | null>(null);
  const [deleteOpen, setDeleteOpen] = useState(false);

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

      {uploadMsg && (
        <p
          className={`text-xs ${uploadMsg.ok ? "text-emerald-600" : "text-red-500"}`}
          role="status"
        >
          {uploadMsg.text}
        </p>
      )}

      {accountId && (
        <KnowledgeUploadDialog
          open={dialogOpen}
          onOpenChange={setDialogOpen}
          kbId={kb.id}
          accountId={accountId}
          onUploaded={(name) => {
            setUploadMsg({ ok: true, text: `已上传 ${name}` });
            documents.reload();
          }}
        />
      )}
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
                      title={file.vectorError ?? file.parseError ?? parseStatusLabel(file)}
                      className={`absolute right-2 top-2 rounded-md px-1.5 py-0.5 text-[10px] font-medium ${
                        PARSE_STATUS_TONE[parseStatusLabel(file)] ??
                        "bg-muted text-muted-foreground"
                      }`}
                    >
                      {parseStatusLabel(file)}
                    </span>
                    {(file.vectorStatus === "queued" || file.vectorStatus === "indexing") && (
                      <span className="absolute left-2 top-6 text-[10px] text-muted-foreground">
                        向量化中 {file.vectorDone ?? 0}/{file.vectorTotal || "…"}
                      </span>
                    )}
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
                    disabled={
                      vectorization.submitting ||
                      file.parseStatus !== "parsed" ||
                      !file.parsedContent?.trim() ||
                      file.vectorStatus === "queued" ||
                      file.vectorStatus === "indexing"
                    }
                    onClick={() => void vectorization.start(file)}
                  >
                    <Network />
                    向量化
                  </ContextMenuItem>
                  <ContextMenuItem
                    className="text-destructive data-[highlighted]:bg-destructive/10 data-[highlighted]:text-destructive [&_svg]:text-destructive"
                    onClick={() => {
                      const anchor = cards.current.get(file.id);
                      if (anchor) {
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

      {accountId && (
        <KnowledgeDeletePopover
          open={deleteOpen && deleteTarget?.kbId === kbId}
          onOpenChange={setDeleteOpen}
          kbId={kbId}
          accountId={accountId}
          target={deleteTarget}
          onDeleted={() => documents.reload()}
        />
      )}
    </div>
  );
}

export function KnowledgeLoadState({
  error,
  reload,
}: {
  error: string | null;
  reload: () => void;
}) {
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
