import { useEffect, useRef, useState } from "react";
import { Link, useNavigate, useSearch } from "@tanstack/react-router";
import {
  ArrowDown,
  ArrowLeft,
  Check,
  Clock3,
  FileText,
  Loader2,
  Pause,
  Play,
  Square,
} from "lucide-react";
import { Button, buttonVariants } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { duration, elapsed, generateMinutes, applyGeneratedMinutes } from "@/apis/meetings";
import { useWorkspace } from "@/stores/meetings";
import { control } from "../lib/recording";
import { useMeetingAsr } from "../hooks/use-meeting-asr";
import { applyAsrTranscript } from "../lib/asr-transcript";
import { SaveStatus } from "./workspace-parts";

export function MeetingSessionPage() {
  const { id } = useSearch({ from: "/_app/meetings/active" });
  const { draft, loading, error, change, preview, retry, editable } = useWorkspace(id);
  const asr = useMeetingAsr(id ?? "", (message) => {
    if (message.segment.isFinal) return change((current) => applyAsrTranscript(current, message));
    preview((current) => applyAsrTranscript(current, message));
  });
  const navigate = useNavigate();
  const [now, setNow] = useState(Date.now);
  const [end, setEnd] = useState(false);
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [following, setFollowing] = useState(true);
  const scroll = useRef<HTMLDivElement>(null);
  const actionLock = useRef(false);
  const [generating, setGenerating] = useState(false);
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, []);
  useEffect(() => {
    if (following) {
      const target = scroll.current;
      if (target) target.scrollTop = target.scrollHeight;
    }
  }, [following, draft?.segments.length, draft?.temporary.text]);
  async function startTranscription() {
    setActionError(null);
    try {
      await asr.start();
    } catch (cause) {
      setActionError(cause instanceof Error ? cause.message : "启动转写失败。");
    }
  }
  async function toggleRecording() {
    if (!editable || actionLock.current) return;
    actionLock.current = true;
    setBusy(true);
    setActionError(null);
    try {
      if (draft?.meeting.status === "active") {
        if (asr.status === "live" || asr.status === "connecting") await asr.stop();
        await change((current) => ({
          ...control(current, "paused"),
          temporary: { speaker: "", text: "" },
        }));
      } else {
        await change((current) => control(current, "active"));
        await asr.start();
      }
    } catch (cause) {
      setActionError(cause instanceof Error ? cause.message : "暂停或恢复失败。");
    } finally {
      actionLock.current = false;
      setBusy(false);
    }
  }
  async function finish() {
    if (!editable || actionLock.current) return;
    actionLock.current = true;
    setBusy(true);
    setActionError(null);
    try {
      if (asr.status === "live" || asr.status === "connecting") await asr.stop();
      await change((current) => ({
        ...control(current, "ended"),
        temporary: { speaker: "", text: "" },
      }));
      setEnd(false);
    } catch (cause) {
      setActionError(cause instanceof Error ? cause.message : "结束失败，请重试");
    } finally {
      actionLock.current = false;
      setBusy(false);
    }
  }
  async function generate() {
    if (!draft || !editable || actionLock.current || draft.meeting.status !== "ended") return;
    actionLock.current = true;
    setGenerating(true);
    setActionError(null);
    try {
      await retry();
      const result = await generateMinutes(draft);
      await change((current) => applyGeneratedMinutes(current, result));
      await navigate({ to: "/meetings", search: { view: "generating" } });
    } catch (cause) {
      setActionError(cause instanceof Error ? cause.message : "生成请求失败，请重试");
    } finally {
      actionLock.current = false;
      setGenerating(false);
    }
  }
  if (!id || error || (!loading && !draft))
    return (
      <div className="m-8 grid gap-4">
        <p role="alert">{error ?? "请从会议列表选择一场会议。"}</p>
        <Link to="/meetings" className={buttonVariants({ variant: "outline" })}>
          返回会议列表
        </Link>
      </div>
    );
  if (!draft) return <p className="p-8 text-muted-foreground">正在恢复会议记录…</p>;
  const live = draft.meeting.status === "active";
  const ended = draft.meeting.status === "ended" || draft.meeting.status === "archived";
  return (
    <div className="flex h-full min-h-0 flex-col gap-4 px-5 py-5 md:px-8">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div className="flex min-w-0 items-start gap-3">
          <Link
            to="/meetings"
            className={buttonVariants({ variant: "ghost", size: "icon" })}
            aria-label="返回会议列表"
          >
            <ArrowLeft className="size-4" />
          </Link>
          <div>
            <div className="flex items-center gap-2">
              <span
                className={`size-2 rounded-full ${live ? "animate-pulse bg-emerald-500" : "bg-amber-500"}`}
              />
              <h1 className="text-lg font-semibold">{draft.meeting.title}</h1>
            </div>
            <p className="mt-1 text-xs text-muted-foreground">
              {ended ? "会议已结束" : live ? "会议进行中" : "会议已暂停"} · 豆包实时转写
            </p>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <span className="mr-3 flex items-center gap-2 font-mono text-lg tabular-nums">
            <Clock3 className="size-4 text-muted-foreground" />
            {duration(elapsed(draft.meeting, now))}
          </span>
          {!ended && live && ["idle", "stopped", "error"].includes(asr.status) && (
            <Button
              variant="outline"
              disabled={!editable || busy}
              onClick={() => void startTranscription()}
            >
              {asr.status === "error" ? "重试转写" : "开始转写"}
            </Button>
          )}
          {["connecting", "stopping"].includes(asr.status) && (
            <span role="status" className="text-xs text-muted-foreground">
              {asr.status === "connecting" ? "正在连接转写服务…" : "正在保存最后的转写…"}
            </span>
          )}
          {!ended && (
            <>
              <Button
                variant="outline"
                disabled={!editable || busy || generating}
                onClick={() => void toggleRecording()}
              >
                {live ? <Pause className="size-4" /> : <Play className="size-4" />}
                {live ? "暂停" : "恢复"}
              </Button>
            </>
          )}
          <Popover
            open={end}
            onOpenChange={(open) => {
              if (!busy) setEnd(open);
            }}
          >
            <PopoverTrigger
              render={
                <Button variant="outline" disabled={!editable || ended || busy || generating}>
                  <Square className="size-3.5" />
                  {ended ? "会议已结束" : "结束会议"}
                </Button>
              }
            />
            <PopoverContent
              align="end"
              className="w-72 max-w-[calc(100vw-2rem)] p-3"
              aria-labelledby="end-meeting-title"
              aria-describedby="end-meeting-description"
            >
              <h2 id="end-meeting-title" className="text-sm font-medium">
                结束本次会议？
              </h2>
              <p id="end-meeting-description" className="mt-1 text-xs text-muted-foreground">
                结束后停止计时，并可生成会议纪要。
              </p>
              {actionError && (
                <p role="alert" className="mt-2 text-xs text-destructive">
                  {actionError}
                </p>
              )}
              <div className="mt-3 flex justify-end gap-2">
                <Button variant="ghost" size="sm" disabled={busy} onClick={() => setEnd(false)}>
                  取消
                </Button>
                <Button
                  variant="destructive"
                  size="sm"
                  disabled={busy}
                  onClick={() => void finish()}
                >
                  {busy && <Loader2 className="size-4 animate-spin" />}
                  {busy ? "正在结束…" : "确认结束"}
                </Button>
              </div>
            </PopoverContent>
          </Popover>
          <Button
            disabled={
              !editable ||
              draft.meeting.status !== "ended" ||
              busy ||
              generating ||
              draft.meeting.minutes_status === 0
            }
            onClick={() => void generate()}
          >
            {generating ? (
              <Loader2 className="size-4 animate-spin" />
            ) : (
              <FileText className="size-4" />
            )}
            {generating
              ? "正在提交…"
              : draft.meeting.minutes_status === 0
                ? "纪要生成中"
                : "生成会议纪要"}
          </Button>
        </div>
      </header>
      <SaveStatus draft={draft} retry={retry} editable={editable} />
      <p role="status" className="text-xs text-muted-foreground">
        {ended
          ? "转写已结束"
          : !live
            ? "转写已暂停"
            : asr.status === "live"
              ? "麦克风录音中 · 正在实时识别"
              : "点击开始转写，使用麦克风记录会议。"}
        {asr.sync && ` · 本地待同步 ${asr.sync.pendingCount} 个片段`}
      </p>
      {asr.error && (
        <p role="alert" className="text-sm text-destructive">
          {asr.error}
        </p>
      )}
      {!editable && (
        <p role="status" className="text-sm text-amber-700">
          当前为只读模式：另一标签页可能正在编辑。关闭该页面后刷新可继续记录。
        </p>
      )}
      {actionError && (
        <p role="alert" className="text-sm text-destructive">
          {actionError}
        </p>
      )}
      <section className="relative flex min-h-36 flex-1 flex-col overflow-hidden rounded-xl border bg-card">
        <div className="flex items-center justify-between border-b px-5 py-3">
          <h2 className="text-sm font-medium">
            会议记录{" "}
            <span className="ml-2 text-xs font-normal text-muted-foreground">
              {draft.segments.length} 个转写片段
            </span>
          </h2>
          <span className="text-xs text-muted-foreground">
            {following ? "跟随最新内容" : "正在查看历史记录"}
          </span>
        </div>
        <div
          ref={scroll}
          onScroll={() => {
            const target = scroll.current;
            if (target)
              setFollowing(target.scrollHeight - target.scrollTop - target.clientHeight < 64);
          }}
          className="min-h-0 flex-1 space-y-5 overflow-y-auto px-5 py-5 md:px-8"
        >
          {!draft.segments.length && (
            <div className="py-10 text-center text-sm text-muted-foreground">
              等待 ASR 转写内容，识别结果将在这里自动显示。
            </div>
          )}
          {draft.segments.map((row) => (
            <article key={row.id} className="group grid grid-cols-[4.5rem_1fr] items-start gap-3">
              <time className="pt-1 font-mono text-xs text-muted-foreground">
                {duration(row.start_ms)}
              </time>
              <div className="min-w-0">
                <div className="mb-1 flex items-center gap-2 text-xs">
                  <span className="font-medium">{row.speaker ?? "未署名"}</span>
                  <span className="flex items-center gap-1 text-muted-foreground">
                    <Check className="size-3" />
                    已定稿
                  </span>
                </div>
                <p className="whitespace-pre-wrap break-words text-sm leading-7">{row.text}</p>
              </div>
            </article>
          ))}
          {draft.temporary.text && (
            <article className="rounded-lg border border-dashed bg-muted/30 p-4">
              <p className="mb-1 text-xs text-muted-foreground">
                {draft.temporary.speaker || "未署名"} · 识别中…
              </p>
              <p className="whitespace-pre-wrap text-sm text-muted-foreground">
                {draft.temporary.text}
              </p>
            </article>
          )}
        </div>
        {!following && (
          <Button
            className="absolute bottom-4 left-1/2 -translate-x-1/2 shadow-lg"
            size="sm"
            onClick={() => {
              if (scroll.current) scroll.current.scrollTop = scroll.current.scrollHeight;
              setFollowing(true);
            }}
          >
            <ArrowDown className="size-4" />
            回到最新
          </Button>
        )}
      </section>
    </div>
  );
}
