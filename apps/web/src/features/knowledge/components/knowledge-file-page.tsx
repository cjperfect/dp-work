import { toast } from "sonner";
import { useParams, Link } from "@tanstack/react-router";
import { useState, useRef, useEffect, useCallback } from "react";
import { ArrowLeft, Network, ScanText } from "lucide-react";
import { Button, buttonVariants } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useKnowledgeDocuments } from "@/features/knowledge/hooks/use-knowledge-documents";
import { useKnowledgeBases } from "@/features/knowledge/hooks/use-knowledge-bases";
import { useAuthStore } from "@/stores/auth";
import { useDocumentPdf } from "@/features/knowledge/hooks/use-document-pdf";
import { useDocumentVectorization } from "@/features/knowledge/hooks/use-document-parsing";
import { renameKnowledgeDocumentRequest } from "@/apis/knowledge";
import { ParsedDocumentEditor } from "./parsed-document-editor";
import { EditableSourceEditor } from "./editable-source-editor";
import { PdfPreview } from "./pdf-preview";
import { DocxPreview } from "./docx-preview";
import { LazyBlockNoteEditor as BlockNoteEditor } from "@/components/editor/lazy-blocknote-editor";
import { ParseDocumentButton } from "./parse-document-button";
import { FILE_TYPE_META } from "@/constants/knowledge";
import { localAccountId } from "@/features/auth/lib/auth";
import { KnowledgeLoadState } from "./knowledge-page";
import { formatDateTime } from "../lib/format-date-time";

export function KnowledgeFilePage() {
  const { kbId, fileId } = useParams({ from: "/_app/knowledge/$kbId/files/$fileId" });

  const { bases, loading, error, reload } = useKnowledgeBases();
  const kb = bases.find((k) => k.id === kbId);
  const documents = useKnowledgeDocuments(kbId);
  const vectorization = useDocumentVectorization(kbId);
  const file = documents.files.find((file) => file.id === fileId);
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
      await renameKnowledgeDocumentRequest(accountId, kbId, file.id, next);
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
              vectorization.submitting ||
              file.parseStatus !== "parsed" ||
              parsedSaveBlocked ||
              !file.parsedContent?.trim() ||
              file.vectorStatus === "queued" ||
              file.vectorStatus === "indexing"
            }
            title={
              parsedSaveBlocked ? "请等待解析文档保存完成" : "先解析并检查文档内容，再进行向量化"
            }
            onClick={() => void vectorization.start(file)}
          >
            <Network className="size-4" />
            {file.vectorStatus === "queued" || file.vectorStatus === "indexing"
              ? `向量化中 ${file.vectorDone ?? 0}/${file.vectorTotal || "…"}`
              : file.vectorStatus === "failed"
                ? "重试向量化"
                : file.vectorizedAt
                  ? "重新向量化"
                  : "向量化"}
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
                <EditableSourceEditor
                  key={`${accountId}:${kb.id}:${file.id}`}
                  accountId={accountId}
                  baseId={kb.id}
                  file={file}
                />
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
            ) : file.type === "docx" && file.storage === "server" && accountId ? (
              <DocxPreview
                key={`${accountId}:${kb.id}:${file.id}`}
                accountId={accountId}
                baseId={kb.id}
                fileId={file.id}
              />
            ) : file.type === "doc" ? (
              <div className="flex min-h-64 flex-col items-center justify-center gap-2 p-8 text-center text-sm text-muted-foreground">
                <Icon className="size-8" />
                <p>旧版 DOC 暂不支持在线预览，请转换为 DOCX 后上传。</p>
              </div>
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
