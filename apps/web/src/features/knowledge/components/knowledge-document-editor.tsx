import { useRef, useState } from "react";
import { Link, useNavigate, useParams } from "@tanstack/react-router";
import { LazyBlockNoteEditor as Editor } from "@/components/editor/lazy-blocknote-editor";
import { ArrowLeft, FileText, Loader2, Save } from "lucide-react";
import { Button, buttonVariants } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useAuthStore } from "@/stores/auth";
import { localAccountId } from "@/features/auth/lib/auth";
import { useKnowledgeBases } from "@/features/knowledge/hooks/use-knowledge-bases";
import { saveKnowledgeDocument } from "@/stores/knowledge";
import type { KbFile, KnowledgeBase } from "../constants/knowledge-data";

export function NewKnowledgeDocumentPage() {
  const { kbId } = useParams({ from: "/_app/knowledge/$kbId/new" });
  return <DocumentPage kbId={kbId} />;
}

export function EditKnowledgeDocumentPage() {
  const { kbId, fileId } = useParams({ from: "/_app/knowledge/$kbId/edit/$fileId" });
  return <DocumentPage kbId={kbId} fileId={fileId} />;
}

function DocumentPage({ kbId, fileId }: { kbId: string; fileId?: string }) {
  const { bases, loading, error, reload } = useKnowledgeBases();
  const accountId = useAuthStore((state) => localAccountId(state.user));
  const base = bases.find((row) => row.id === kbId);
  const file = base?.files.find((row) => row.id === fileId);
  if (loading || error)
    return (
      <div className="grid gap-4 p-8">
        <p role={error ? "alert" : "status"} className="text-sm text-muted-foreground">
          {error ?? "正在读取文档…"}
        </p>
        {error && (
          <Button variant="outline" className="w-fit" onClick={reload}>
            重新加载
          </Button>
        )}
      </div>
    );
  if (!accountId || !base || (fileId && (!file || file.source !== "editor")))
    return (
      <div className="grid gap-4 p-8">
        <p>知识库或文档不存在，或此文档不支持在线编辑。</p>
        <Link
          to="/knowledge"
          className={buttonVariants({ variant: "outline", className: "w-fit" })}
        >
          返回知识库
        </Link>
      </div>
    );
  return (
    <DocumentForm
      key={`${accountId}:${kbId}:${fileId ?? "new"}`}
      accountId={accountId}
      base={base}
      initialFile={file}
    />
  );
}

function DocumentForm({
  accountId,
  base,
  initialFile,
}: {
  accountId: string;
  base: KnowledgeBase;
  initialFile?: KbFile;
}) {
  const navigate = useNavigate();
  const [id] = useState(() => initialFile?.id ?? `editor-${crypto.randomUUID()}`);
  const [title, setTitle] = useState(() => initialFile?.name.replace(/\.md$/i, "") ?? "");
  const [content, setContent] = useState(initialFile?.content ?? "");
  const [blocks, setBlocks] = useState(initialFile?.blocks);
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState<"draft" | "published" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState(
    initialFile?.status === "draft" ? "草稿已保存" : initialFile ? "已保存" : "尚未保存",
  );
  const lock = useRef(false);
  const titleRef = useRef<HTMLInputElement>(null);

  async function save(status: "draft" | "published") {
    if (lock.current) return;
    if (!title.trim().replace(/\.md$/i, "").trim()) {
      setError("请输入文档标题。");
      titleRef.current?.focus();
      return;
    }
    lock.current = true;
    setSaving(status);
    setError(null);
    try {
      const file = await saveKnowledgeDocument(accountId, base.id, {
        id,
        title,
        content,
        blocks,
        status,
      });
      if (localAccountId(useAuthStore.getState().user) !== accountId) return;
      setDirty(false);
      setNotice(status === "draft" ? "草稿已保存" : "已保存");
      if (status === "published")
        await navigate({
          to: "/knowledge/$kbId/files/$fileId",
          params: { kbId: base.id, fileId: file.id },
        });
      else if (!initialFile)
        await navigate({
          to: "/knowledge/$kbId/edit/$fileId",
          params: { kbId: base.id, fileId: file.id },
          replace: true,
        });
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "保存失败，请重试。");
    } finally {
      lock.current = false;
      setSaving(null);
    }
  }

  return (
    <div className="flex h-full min-h-0 flex-col gap-5 px-6 py-6 md:px-10">
      <header className="flex flex-wrap items-center justify-between gap-4">
        <div className="flex min-w-0 items-center gap-3">
          <Link
            to="/knowledge/$kbId"
            params={{ kbId: base.id }}
            className={buttonVariants({ variant: "ghost", size: "icon" })}
            aria-label="返回知识库"
          >
            <ArrowLeft className="size-4" />
          </Link>
          <div className="min-w-0">
            <h1 className="flex items-center gap-2 text-lg font-semibold">
              <FileText className="size-4" />
              {initialFile ? "编辑文档" : "新建文档"}
            </h1>
            <p className="mt-1 truncate text-xs text-muted-foreground">{base.name}</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" disabled={saving !== null} onClick={() => void save("draft")}>
            {saving === "draft" && <Loader2 className="size-4 animate-spin" />}保存草稿
          </Button>
          <Button disabled={saving !== null} onClick={() => void save("published")}>
            {saving === "published" ? (
              <Loader2 className="size-4 animate-spin" />
            ) : (
              <Save className="size-4" />
            )}
            保存
          </Button>
        </div>
      </header>
      <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-muted-foreground">
        <p>保存草稿后可继续编辑；保存后进入文档阅读页。</p>
        <span role="status">{saving ? "保存中…" : dirty ? "有未保存的修改" : notice}</span>
      </div>
      {error && (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      )}
      <section className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-xl border bg-card">
        <div className="border-b px-5 py-4">
          <label className="sr-only" htmlFor="knowledge-document-title">
            文档标题
          </label>
          <Input
            ref={titleRef}
            id="knowledge-document-title"
            value={title}
            disabled={saving !== null}
            onChange={(event) => {
              setTitle(event.target.value);
              setDirty(true);
              setError(null);
            }}
            placeholder="请输入文档标题"
            className="h-11 border-0 px-0 text-xl! font-semibold shadow-none focus-visible:ring-0"
          />
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto" aria-label="文档富文本编辑器">
          <Editor
            initialContent={blocks}
            markdown={blocks ? undefined : content}
            editable={saving === null}
            className="px-2 py-5 md:px-5"
            onDocumentChange={({ blocks: nextBlocks, markdown }) => {
              setBlocks(nextBlocks);
              setContent(markdown);
              setDirty(true);
            }}
          />
        </div>
      </section>
    </div>
  );
}
