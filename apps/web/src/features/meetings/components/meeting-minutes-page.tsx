import { useCallback, useRef, useState } from "react";
import { Link, useNavigate, useSearch } from "@tanstack/react-router";
import { LazyMinutesMindMap as MindMap } from "./lazy-minutes-mind-map";
import { ArrowLeft, Archive, FileText, Sparkles } from "lucide-react";
import { Button, buttonVariants } from "@/components/ui/button";
import { archiveMinutes } from "@/apis/meeting-records";
import { Textarea } from "@/components/ui/textarea";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { updateTranscriptText } from "../lib/recording";
import { useKnowledgeBases } from "@/features/knowledge/hooks/use-knowledge-bases";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog";
import { duration, elapsed, generateMinutes, STATUS_LABELS } from "@/apis/meetings";
import { useWorkspace, cacheServerWorkspace, loadWorkspace } from "@/stores/meeting";
import { readDraft } from "../lib/workspace-storage";
import { minutesContent, originalMeetingContent } from "../lib/minutes-content";
import { canEditMinutes, generationStatus, showOriginalMeeting } from "../lib/minutes-state";
import { useGenerationEvents } from "../hooks/use-generation-events";
import { RecordWorkspace } from "./record-workspace";
import { SaveStatus } from "./workspace-parts";

export function MeetingMinutesPage() {
  const { id } = useSearch({ from: "/_app/meetings/minutes" });
  const navigate = useNavigate();
  const { draft, loading, error, change, retry, accountId, editable } = useWorkspace(id);
  const [archive, setArchive] = useState(false);
  const { bases, error: kbError, loading: kbLoading, reload } = useKnowledgeBases(archive);
  const actionLock = useRef(false);
  const recordFlush = useRef<(() => Promise<void>) | null>(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [failure, setFailure] = useState<string | null>(null);
  const [baseId, setBaseId] = useState("");
  const [published, setPublished] = useState<{
    document_id: string;
    knowledge_base_id: string;
  } | null>(null);
  useGenerationEvents(draft?.meeting.generation_status === "generating", (updates) => {
    const latest = updates.find((row) => row.id === id);
    if (accountId && id && latest && latest.revision > (draft?.meeting.revision ?? 0)) {
      void loadWorkspace(accountId, id).catch(() =>
        setFailure("读取最新纪要失败，请重新进入页面。"),
      );
    }
  });
  const [collaborative, setCollaborative] = useState<{ id: string; content: string } | null>(null);
  const onMinutesContent = useCallback(
    (content: string) => {
      if (!id) return;
      setCollaborative((previous) =>
        previous?.id === id && previous.content === content ? previous : { id, content },
      );
    },
    [id],
  );
  async function publishMinutes() {
    if (!id || !accountId || !baseId) return;
    setBusy(true);
    setFailure(null);
    try {
      if (!recordFlush.current) throw new Error("纪要编辑器尚未就绪，请稍后重试。");
      await recordFlush.current();
      const archived = await archiveMinutes(id, Number(baseId.replace(/^server-/, "")));
      cacheServerWorkspace(archived);
      const documentId = archived.minutes?.archived_document_id;
      if (!documentId) throw new Error("归档文档不存在。");
      setPublished({ document_id: String(documentId), knowledge_base_id: baseId });
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
    if (!draft || draft.meeting.owner_id !== accountId || !accountId || !id || actionLock.current)
      return;
    actionLock.current = true;
    setBusy(true);
    setFailure(null);
    try {
      await retry();
      const current = await readDraft(accountId, id);
      if (!current) throw new Error("会议不存在或已删除。");
      const result = await generateMinutes(current);
      cacheServerWorkspace({ ...current, meeting: result.meeting });
      await navigate({ to: "/meetings", search: { view: "pending" } });
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
  const showOriginal = showOriginalMeeting(draft.meeting);
  const content = showOriginal
    ? originalMeetingContent(draft)
    : collaborative?.id === id
      ? collaborative.content
      : minutesContent(draft);
  const status = generationStatus(draft.meeting);
  const canEdit = !showOriginal && canEditMinutes(draft.meeting);
  const canEditOriginal =
    showOriginal && editable && draft.meeting.status === "ended" && status !== "generating";
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
            <p className="mb-1 text-xs tracking-widest text-muted-foreground">
              {showOriginal ? "MEETING RECORD" : "MEETING MINUTES"}
            </p>
            <h1 className="text-lg font-semibold">{draft.meeting.title}</h1>
            <p className="mt-1 text-xs text-muted-foreground">
              {STATUS_LABELS[draft.meeting.status]} · {duration(elapsed(draft.meeting))} ·{" "}
              {showOriginal
                ? canEditOriginal
                  ? "原始转写 · 可编辑"
                  : "原始转写 · 只读"
                : canEdit
                  ? "可编辑"
                  : "只读"}
            </p>
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          {(status === "idle" || status === "failed") && draft.meeting.status === "ended" && (
            <Button
              disabled={busy || draft.meeting.owner_id !== accountId}
              onClick={() => void regenerate()}
            >
              <Sparkles className="size-4" />
              {busy ? "正在提交…" : "生成会议纪要"}
            </Button>
          )}
          {!showOriginal && draft.meeting.status !== "archived" && (
            <Button
              disabled={
                busy ||
                draft.meeting.owner_id !== accountId ||
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
      {showOriginal && <SaveStatus draft={draft} retry={retry} editable={editable} />}
      {showOriginal && !editable && (
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
                fileId: published.document_id,
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
      <div
        className={`grid min-h-0 flex-1 gap-4 overflow-y-auto lg:overflow-hidden ${showOriginal ? "grid-cols-1" : "lg:grid-cols-2"}`}
      >
        <section className="flex min-h-0 flex-col overflow-hidden rounded-xl border bg-card">
          <div className="flex flex-wrap items-center justify-between gap-2 border-b px-5 py-3">
            <h2 className="flex items-center gap-2 text-sm font-medium">
              <FileText className="size-4" />
              {showOriginal ? "会议原始内容" : "会议纪要"}{" "}
              <span className="text-xs font-normal text-muted-foreground">
                {showOriginal
                  ? canEditOriginal
                    ? "可编辑"
                    : "只读"
                  : draft.meeting.status === "archived"
                    ? "已归档"
                    : canEdit
                      ? "可编辑"
                      : "只读"}
              </span>
            </h2>
            <div className="flex items-center gap-2">
              {!showOriginal && (
                <span className="text-xs text-muted-foreground">{content.length} 字</span>
              )}
            </div>
          </div>
          {showOriginal ? (
            <div className="min-h-0 flex-1 space-y-4 overflow-auto p-5" aria-label="会议原始转写">
              {draft.segments.length ? (
                draft.segments.map((row) => (
                  <article key={row.id} className="grid grid-cols-[4.5rem_1fr] items-start gap-3">
                    <time className="pt-1 font-mono text-xs text-muted-foreground">
                      {duration(row.start_ms)}
                    </time>
                    <div className="min-w-0">
                      <p className="mb-1 text-xs font-medium">{row.speaker ?? "未署名"}</p>
                      {canEditOriginal ? (
                        <Textarea
                          key={row.revision}
                          aria-label={`修正转写 ${duration(row.start_ms)}`}
                          defaultValue={row.text}
                          disabled={busy}
                          className="min-h-0 resize-none border-transparent px-1 py-0 text-sm leading-7 shadow-none hover:border-input focus-visible:ring-1"
                          onBlur={(event) => {
                            const text = event.currentTarget.value;
                            if (text !== row.text)
                              void change((current) => updateTranscriptText(current, row.id, text));
                          }}
                        />
                      ) : (
                        <p className="whitespace-pre-wrap break-words text-sm leading-7">
                          {row.text}
                        </p>
                      )}
                    </div>
                  </article>
                ))
              ) : (
                <p className="text-sm text-muted-foreground">暂无会议转写记录。</p>
              )}
            </div>
          ) : (
            <RecordWorkspace
              meetingId={draft.meeting.id}
              flushRef={recordFlush}
              disabled={busy}
              onContentChange={onMinutesContent}
            />
          )}
        </section>
        {!showOriginal && (
          <section className="flex min-h-96 flex-col overflow-hidden rounded-xl border bg-card lg:min-h-0">
            <div className="border-b px-5 py-3">
              <h2 className="text-sm font-medium">重点思维导图</h2>
              <p className="mt-1 text-xs text-muted-foreground">
                可拖动节点调整位置 · 支持缩放、拖动画布
              </p>
            </div>
            <div className="min-h-0 flex-1">
              <MindMap title={draft.meeting.title} content={content} />
            </div>
          </section>
        )}
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
          <div className="grid gap-2 text-sm">
            <label htmlFor="meeting-archive-knowledge">目标知识库</label>
            <Select
              value={baseId || null}
              items={bases.map((base) => ({ value: base.id, label: base.name }))}
              onValueChange={(value) => setBaseId(typeof value === "string" ? value : "")}
              disabled={busy || kbLoading}
            >
              <SelectTrigger
                id="meeting-archive-knowledge"
                aria-label="目标知识库"
                className="w-full"
              >
                <SelectValue placeholder="请选择知识库" />
              </SelectTrigger>
              <SelectContent className="w-[var(--anchor-width)]">
                {bases.map((base) => (
                  <SelectItem key={base.id} value={base.id}>
                    {base.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
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
