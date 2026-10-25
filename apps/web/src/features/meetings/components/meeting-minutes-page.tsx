import { useRef, useState } from "react";
import { Link, useNavigate, useSearch } from "@tanstack/react-router";
import { LazyBlockNoteEditor as Preview } from "@/components/editor/lazy-blocknote-editor";
import { LazyMinutesMindMap as MindMap } from "./lazy-minutes-mind-map";
import { ArrowLeft, Archive, Download, FileText, Save, Sparkles } from "lucide-react";
import { Button, buttonVariants } from "@/components/ui/button";
import { addKnowledgeDocument } from "@/features/knowledge/lib/knowledge-repository";
import { useKnowledgeBases } from "@/features/knowledge/hooks/use-knowledge-bases";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog";
import {
  duration,
  elapsed,
  exportMarkdown,
  generateMinutes,
  applyGeneratedMinutes,
  STATUS_LABELS,
  type Workspace,
} from "@/apis/meetings";
import { publish, useWorkspace } from "@/stores/meetings";
import { readDraft, replaceFromServer } from "../lib/workspace-storage";
import { canEditMinutes, generationStatus } from "../lib/minutes-state";
import { MinutesShare } from "./minutes-share";
import { SaveStatus } from "./workspace-parts";

export function MeetingMinutesPage() {
  const { id } = useSearch({ from: "/_app/meetings/minutes" });
  const navigate = useNavigate();
  const { draft, loading, error, change, retry, accountId, editable } = useWorkspace(id);
  const { bases, error: kbError, loading: kbLoading, reload } = useKnowledgeBases();
  const actionLock = useRef(false);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [failure, setFailure] = useState<string | null>(null);
  const [archive, setArchive] = useState(false);
  const [baseId, setBaseId] = useState("");
  const [preview, setPreview] = useState(false);
  const [published, setPublished] = useState<{
    document_id: string;
    knowledge_base_id: string;
  } | null>(null);
  async function save() {
    setBusy(true);
    setFailure(null);
    setNotice(null);
    try {
      await retry();
      setNotice("纪要草稿已保存。");
    } catch (cause) {
      setFailure(cause instanceof Error ? cause.message : "保存失败");
    } finally {
      setBusy(false);
    }
  }
  async function publishMinutes() {
    if (!id || !accountId || !baseId) return;
    setBusy(true);
    setFailure(null);
    try {
      await retry();
      const current = await readDraft(accountId, id);
      if (!current) throw new Error("未找到已保存的会议。");
      // 业务 API 已下线：本地归档（标记已归档 + 纪要已生成），不发起请求。
      const now = new Date().toISOString();
      const documentId = `meeting-${id}`;
      await addKnowledgeDocument(`user:${accountId}`, baseId, {
        id: `doc-${documentId}`,
        name: `${current.meeting.title}.md`,
        type: "md",
        content: current.minutes?.content ?? "",
        size: `${Math.max(1, Math.ceil(new Blob([current.minutes?.content ?? ""]).size / 1024))} KB`,
        uploader: "我",
        updatedAt: now.slice(0, 10),
      });
      const archived: Workspace = {
        ...current,
        meeting: {
          ...current.meeting,
          status: "archived",
          ended_at: current.meeting.ended_at ?? now,
          updated_at: now,
        },
        minutes: current.minutes
          ? { ...current.minutes, status: 1 }
          : { content: "", status: 1, archived_document_id: null },
      };
      const fresh = await replaceFromServer(archived);
      publish(fresh);
      setPublished({ document_id: documentId, knowledge_base_id: baseId });
      setArchive(false);
      setNotice("会议纪要已归档。");
      reload();
    } catch (cause) {
      setFailure(cause instanceof Error ? cause.message : "归档失败，草稿已保留");
    } finally {
      setBusy(false);
    }
  }
  async function regenerate() {
    if (!draft || !editable || actionLock.current) return;
    actionLock.current = true;
    setBusy(true);
    setFailure(null);
    try {
      await retry();
      const result = await generateMinutes(draft);
      await change((current) => applyGeneratedMinutes(current, result));
      await navigate({ to: "/meetings", search: { view: "generating" } });
    } catch (cause) {
      setFailure(cause instanceof Error ? cause.message : "提交失败，请重试");
    } finally {
      actionLock.current = false;
      setBusy(false);
    }
  }
  if (!id || error || (!loading && !draft))
    return (
      <div className="m-8 grid gap-4">
        <p role="alert">{error ?? "请从会议列表选择会议。"}</p>
        <Link to="/meetings" className={buttonVariants({ variant: "outline" })}>
          返回会议列表
        </Link>
      </div>
    );
  if (!draft) return <p className="p-8 text-muted-foreground">正在恢复会议纪要…</p>;
  const content = draft.minutes?.content ?? "";
  const status = generationStatus(draft.meeting);
  const canEdit = editable && canEditMinutes(draft.meeting);
  const ended = draft.meeting.status === "ended" || draft.meeting.status === "archived";
  return (
    <div className="flex h-full min-h-0 flex-col gap-4 px-5 py-5 md:px-8">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div className="flex gap-3">
          <Link
            to="/meetings"
            className={buttonVariants({ variant: "ghost", size: "icon" })}
            aria-label="返回会议列表"
          >
            <ArrowLeft className="size-4" />
          </Link>
          <div>
            <p className="mb-1 text-xs tracking-widest text-muted-foreground">MEETING MINUTES</p>
            <h1 className="text-lg font-semibold">{draft.meeting.title}</h1>
            <p className="mt-1 text-xs text-muted-foreground">
              {STATUS_LABELS[draft.meeting.status]} · {duration(elapsed(draft.meeting))} ·{" "}
              {canEdit ? "可编辑" : "只读"}
            </p>
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          <MinutesShare workspace={draft} beforeShare={retry} />
          {(status === "idle" || status === "failed") && draft.meeting.status === "ended" && (
            <Button disabled={busy || !editable} onClick={() => void regenerate()}>
              <Sparkles className="size-4" />
              {busy ? "正在提交…" : "生成会议纪要"}
            </Button>
          )}
          <Button
            variant="outline"
            disabled={busy}
            onClick={() => exportMarkdown(draft.meeting.title, content)}
          >
            <Download className="size-4" />
            导出 Markdown
          </Button>
          {canEdit && (
            <Button variant="outline" disabled={busy} onClick={() => void save()}>
              <Save className="size-4" />
              {busy ? "处理中…" : "保存草稿"}
            </Button>
          )}
          {draft.meeting.status !== "archived" && (
            <Button
              disabled={
                busy ||
                !editable ||
                !ended ||
                !content.trim() ||
                status === "generating" ||
                status === "failed"
              }
              onClick={() => {
                setFailure(null);
                setArchive(true);
              }}
            >
              <Archive className="size-4" />
              归档到知识库
            </Button>
          )}
        </div>
      </header>
      <SaveStatus draft={draft} retry={retry} editable={editable} />
      {!editable && (
        <p className="text-sm text-amber-700" role="status">
          当前为只读模式，另一标签页可能正在编辑。关闭该页面后刷新可继续编辑。
        </p>
      )}
      {notice && (
        <p role="status" className="text-sm text-emerald-700">
          {notice}
          {published && (
            <Link
              to="/knowledge/$kbId/files/$fileId"
              params={{
                kbId: String(published.knowledge_base_id),
                fileId: `doc-${published.document_id}`,
              }}
              className="ml-3 underline"
            >
              查看归档文档
            </Link>
          )}
        </p>
      )}
      {failure && !archive && (
        <p role="alert" className="text-sm text-destructive">
          {failure}
        </p>
      )}
      {!ended && (
        <p className="text-sm text-muted-foreground">
          会议仍在进行。可以先写草稿，结束会议后归档。
          <Link to="/meetings/active" search={{ id }} className="ml-2 underline">
            返回会议记录
          </Link>
        </p>
      )}
      {status === "generating" && (
        <p role="status" className="text-sm text-muted-foreground">
          AI 正在生成会议纪要，当前内容仅供查看。
        </p>
      )}
      {status === "failed" && (
        <p role="alert" className="text-sm text-destructive">
          {draft.meeting.generation_error || "会议纪要生成失败，可点击上方按钮重新生成。"}
        </p>
      )}
      <div className="grid min-h-0 flex-1 gap-4 overflow-y-auto lg:grid-cols-2 lg:overflow-hidden">
        <section className="flex min-h-0 flex-col overflow-hidden rounded-xl border bg-card">
          <div className="flex flex-wrap items-center justify-between gap-2 border-b px-5 py-3">
            <h2 className="flex items-center gap-2 text-sm font-medium">
              <FileText className="size-4" />
              会议纪要{" "}
              <span className="text-xs font-normal text-muted-foreground">
                {draft.meeting.status === "archived" ? "已归档" : canEdit ? "可编辑" : "只读"}
              </span>
            </h2>
            <div className="flex items-center gap-2">
              <span className="text-xs text-muted-foreground">{content.length} 字</span>
              {canEdit && (
                <Button size="xs" variant="ghost" onClick={() => setPreview((value) => !value)}>
                  {preview ? "继续编辑" : "阅读预览"}
                </Button>
              )}
            </div>
          </div>
          {preview || !canEdit ? (
            <div className="min-h-0 flex-1 overflow-auto">
              {content.trim() ? (
                <Preview
                  key={draft.meeting.id}
                  initialContent={draft.minutes?.blocks}
                  markdown={draft.minutes?.blocks ? undefined : content}
                  editable={false}
                  className="p-5"
                />
              ) : (
                <p className="p-5 text-sm text-muted-foreground">
                  {status === "generating" ? "会议纪要生成中，请稍后查看。" : "暂无会议纪要内容。"}
                </p>
              )}
            </div>
          ) : (
            <div className="min-h-0 flex-1 overflow-auto" aria-label="会议纪要富文本编辑器">
              <Preview
                key={draft.meeting.id}
                initialContent={draft.minutes?.blocks}
                markdown={draft.minutes?.blocks ? undefined : content}
                editable={!busy && canEdit}
                className="p-5"
                onDocumentChange={({ blocks, markdown }) => {
                  setNotice(null);
                  void change((current) => ({
                    ...current,
                    dirtyMinutes: true,
                    minutes: {
                      content: markdown,
                      blocks,
                      status: 1,
                      archived_document_id: current.minutes?.archived_document_id ?? null,
                    },
                  }));
                }}
              />
            </div>
          )}
        </section>
        <section className="flex min-h-96 flex-col overflow-hidden rounded-xl border bg-card lg:min-h-0">
          <div className="border-b px-5 py-3">
            <h2 className="text-sm font-medium">重点思维导图</h2>
            <p className="mt-1 text-xs text-muted-foreground">
              按纪要标题与条目组织 · 可缩放、拖动画布
            </p>
          </div>
          <div className="min-h-0 flex-1">
            <MindMap title={draft.meeting.title} content={content} />
          </div>
        </section>
      </div>
      <Dialog
        open={archive}
        onOpenChange={(open) => {
          if (!busy) setArchive(open);
        }}
      >
        <DialogContent showCloseButton={!busy}>
          <DialogHeader>
            <DialogTitle>归档会议纪要</DialogTitle>
            <DialogDescription>
              先同步最新草稿，再保存为知识库中的 Markdown 文档。再次归档会更新原文档。
            </DialogDescription>
          </DialogHeader>
          <label className="grid gap-2 text-sm">
            目标知识库
            <select
              aria-label="目标知识库"
              className="h-10 rounded-md border bg-background px-3"
              value={baseId}
              onChange={(e) => setBaseId(e.target.value)}
              disabled={busy || kbLoading}
            >
              <option value="">请选择知识库</option>
              {bases.map((base) => (
                <option key={base.id} value={base.id}>
                  {base.name}
                </option>
              ))}
            </select>
          </label>
          {!kbLoading && !bases.length && (
            <p className="text-sm text-muted-foreground">请先在知识库页面创建一个知识库。</p>
          )}
          {(kbError || failure) && (
            <p role="alert" className="text-sm text-destructive">
              {failure ?? kbError}
            </p>
          )}
          <DialogFooter>
            <Button variant="outline" disabled={busy} onClick={() => setArchive(false)}>
              取消
            </Button>
            <Button
              disabled={busy || !baseId || kbLoading || !!kbError}
              onClick={() => void publishMinutes()}
            >
              {busy ? "正在归档…" : "确认归档"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
