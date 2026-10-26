import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "@tanstack/react-router";
import { LazyBlockNoteEditor as Editor } from "@/components/editor/lazy-blocknote-editor";
import { ArrowLeft, FileText } from "lucide-react";
import { Button, buttonVariants } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useAuthStore } from "@/stores/auth";
import { localAccountId } from "@/features/auth/lib/auth";
import { useKnowledgeDocuments } from "@/features/knowledge/hooks/use-knowledge-documents";
import { useKnowledgeBases } from "@/features/knowledge/hooks/use-knowledge-bases";
import { saveKnowledgeDocument } from "@/stores/knowledge";
import type { EditorDocumentInput } from "../lib/knowledge-repository";
import { ParseDocumentButton } from "./parse-document-button";
import type { KbFile, KnowledgeBase } from "../constants/knowledge-data";

function savedDate(value: string | null): Date | null {
  if (!value) return null;
  // SQLite 返回的无时区时间按服务端 UTC 解释。
  const timestamp = /T/.test(value) && !/(Z|[+-]\d{2}:\d{2})$/i.test(value) ? `${value}Z` : value;
  const date = new Date(timestamp);
  return Number.isNaN(date.getTime()) ? null : date;
}

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
  const documents = useKnowledgeDocuments(kbId);
  const file =
    documents.files.find((row) => row.id === fileId) ??
    base?.files.find((row) => row.id === fileId);
  const loadError = error ?? documents.error;
  if ((loading && !base) || loadError || (fileId && documents.loading && !file))
    return (
      <div className="grid gap-4 p-8">
        <p role={loadError ? "alert" : "status"} className="text-sm text-muted-foreground">
          {loadError ?? "正在读取文档…"}
        </p>
        {loadError && (
          <Button
            variant="outline"
            className="w-fit"
            onClick={() => {
              reload();
              documents.reload();
            }}
          >
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
  const [title, setTitle] = useState(() => initialFile?.name.replace(/\.md$/i, "") ?? "未命名文档");
  const [editingTitle, setEditingTitle] = useState(false);
  const [titleDraft, setTitleDraft] = useState(title);
  const titleInput = useRef<HTMLInputElement>(null);
  const titleButton = useRef<HTMLButtonElement>(null);
  const cancelTitle = useRef(false);
  const restoreTitleFocus = useRef(false);
  const [content] = useState(initialFile?.content ?? "");
  const [blocks] = useState(initialFile?.blocks);
  const [revision, setRevision] = useState(0);
  const [dirty, setDirty] = useState(!initialFile);
  const [saving, setSaving] = useState(false);
  const [savedAt, setSavedAt] = useState<string | null>(initialFile?.updatedAt ?? null);
  const [error, setError] = useState<string | null>(null);
  const pending = useRef<EditorDocumentInput | null>(
    initialFile
      ? null
      : {
          id,
          title,
          content,
          blocks,
          status: "published",
        },
  );
  const document = useRef({ title, content, blocks });
  const savingRef = useRef(false);
  const mounted = useRef(false);
  const isNew = !initialFile;
  const retryTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const retryCount = useRef(0);

  const save = useCallback(
    async function persist() {
      const snapshot = pending.current;
      if (!snapshot || savingRef.current) return;
      if (localAccountId(useAuthStore.getState().user) !== accountId) return;
      if (retryTimer.current) clearTimeout(retryTimer.current);
      retryTimer.current = null;
      savingRef.current = true;
      let succeeded = false;
      if (mounted.current) {
        setSaving(true);
        setError(null);
      }
      try {
        const file = await saveKnowledgeDocument(accountId, base.id, snapshot);
        succeeded = true;
        if (mounted.current && localAccountId(useAuthStore.getState().user) === accountId)
          setSavedAt(file.updatedAt);
        retryCount.current = 0;
        if (pending.current === snapshot) {
          pending.current = null;
          if (mounted.current) setDirty(false);
        }
        if (
          mounted.current &&
          isNew &&
          !pending.current &&
          localAccountId(useAuthStore.getState().user) === accountId
        ) {
          await navigate({
            to: "/knowledge/$kbId/edit/$fileId",
            params: { kbId: base.id, fileId: file.id },
            replace: true,
          });
        }
      } catch (cause) {
        if (mounted.current) {
          setError(cause instanceof Error ? cause.message : "自动保存失败，请重试。");
          const delay = Math.min(2000 * 2 ** Math.min(retryCount.current++, 4), 30000);
          retryTimer.current = setTimeout(() => {
            retryTimer.current = null;
            void persist();
          }, delay);
        }
      } finally {
        savingRef.current = false;
        if (mounted.current) setSaving(false);
        if (succeeded && pending.current && pending.current !== snapshot) void persist();
      }
    },
    [accountId, base.id, isNew, navigate],
  );

  useEffect(() => {
    mounted.current = true;
    const createTimer = isNew
      ? setTimeout(() => {
          void save();
        }, 0)
      : null;
    const interval = setInterval(() => {
      if (!retryTimer.current) void save();
    }, 5000);
    const flush = () => {
      void save();
    };
    const onVisibility = () => {
      if (window.document.visibilityState === "hidden") flush();
    };
    window.addEventListener("pagehide", flush);
    window.document.addEventListener("visibilitychange", onVisibility);
    return () => {
      mounted.current = false;
      if (createTimer) clearTimeout(createTimer);
      clearInterval(interval);
      if (retryTimer.current) clearTimeout(retryTimer.current);
      retryTimer.current = null;
      window.removeEventListener("pagehide", flush);
      window.document.removeEventListener("visibilitychange", onVisibility);
      flush();
    };
  }, [isNew, save]);

  useEffect(() => {
    if (!revision) return;
    const timer = window.setTimeout(() => {
      if (!retryTimer.current) void save();
    }, 1000);
    return () => window.clearTimeout(timer);
  }, [revision, save]);

  function updateDocument(change: Partial<typeof document.current>) {
    document.current = { ...document.current, ...change };
    pending.current = {
      ...document.current,
      id,
      title: document.current.title.trim().replace(/\.md$/i, "").trim() || "未命名文档",
      status: "published",
    };
    setDirty(true);
    setRevision((value) => value + 1);
  }

  useEffect(() => {
    if (editingTitle) {
      titleInput.current?.focus();
      titleInput.current?.select();
    } else if (restoreTitleFocus.current) {
      restoreTitleFocus.current = false;
      titleButton.current?.focus();
    }
  }, [editingTitle]);

  function finishTitle() {
    setEditingTitle(false);
    if (cancelTitle.current) {
      cancelTitle.current = false;
      return;
    }
    const next = titleDraft.trim().replace(/\.md$/i, "").trim() || "未命名文档";
    if (next !== title) {
      setTitle(next);
      updateDocument({ title: next });
      void save();
    }
  }

  const lastSaved = savedDate(savedAt);
  const displayTitle = title.trim().replace(/\.md$/i, "").trim() || "未命名文档";

  return (
    <div className="flex h-full min-h-0 flex-col gap-5 px-6 py-6 md:px-10">
      <header className="flex flex-wrap items-center justify-between gap-4">
        <div className="flex min-w-0 flex-1 items-center gap-3">
          <Link
            to="/knowledge/$kbId"
            params={{ kbId: base.id }}
            className={buttonVariants({ variant: "ghost", size: "icon" })}
            aria-label="返回知识库"
          >
            <ArrowLeft className="size-4" />
          </Link>
          <span
            className="max-w-[40%] shrink-0 truncate text-sm text-muted-foreground"
            title={`知识库：${base.name}`}
          >
            知识库：{base.name}
          </span>
          <div className="min-w-0 flex-1">
            <h1 className="flex min-w-0 items-center gap-2 text-lg font-semibold">
              <FileText className="size-4 shrink-0" />
              {editingTitle ? (
                <Input
                  ref={titleInput}
                  id="knowledge-document-title"
                  aria-label="文档标题"
                  value={titleDraft}
                  onChange={(event) => setTitleDraft(event.target.value)}
                  onBlur={finishTitle}
                  onKeyDown={(event) => {
                    if (event.nativeEvent.isComposing) return;
                    if (event.key === "Enter" || event.key === "Escape") {
                      event.preventDefault();
                      cancelTitle.current = event.key === "Escape";
                      restoreTitleFocus.current = true;
                      event.currentTarget.blur();
                    }
                  }}
                  placeholder="未命名文档"
                  className="h-8 max-w-md text-lg! font-semibold"
                />
              ) : (
                <button
                  ref={titleButton}
                  type="button"
                  aria-label={`修改文档标题：${displayTitle}`}
                  title="点击修改标题"
                  className="max-w-full truncate rounded-sm py-0.5 text-left outline-none hover:text-foreground/75 focus-visible:ring-2 focus-visible:ring-ring"
                  onClick={() => {
                    setTitleDraft(title);
                    setEditingTitle(true);
                  }}
                >
                  {displayTitle}
                </button>
              )}
            </h1>
          </div>
        </div>
        <div className="flex shrink-0 flex-wrap items-center gap-2 text-xs text-muted-foreground">
          {initialFile && (
            <ParseDocumentButton baseId={base.id} file={initialFile} disabled={dirty || saving} />
          )}
          <span role={error ? "alert" : "status"} title={error ?? undefined}>
            {error ? "保存失败" : saving || dirty ? "保存中…" : lastSaved ? "" : "尚未保存"}
          </span>
          {lastSaved && (
            <span>
              最近保存于{" "}
              <time dateTime={lastSaved.toISOString()}>
                {lastSaved.toLocaleString("zh-CN", { hour12: false })}
              </time>
            </span>
          )}
          {error && (
            <Button
              variant="link"
              className="h-auto px-1 py-0 text-xs text-destructive"
              onClick={() => void save()}
            >
              重试
            </Button>
          )}
        </div>
      </header>
      <section className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-xl border bg-card">
        <div className="min-h-0 flex-1 overflow-y-auto" aria-label="文档富文本编辑器">
          <Editor
            initialContent={blocks}
            markdown={blocks ? undefined : content}
            editable
            className="px-2 py-5 md:px-5"
            onDocumentChange={({ blocks: nextBlocks, markdown }) => {
              updateDocument({ blocks: nextBlocks, content: markdown });
            }}
          />
        </div>
      </section>
    </div>
  );
}
