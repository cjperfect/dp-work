"use client";

import { ArrowLeft, Pause, Play, Sparkles, Square } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate, useBlocker } from "@tanstack/react-router";
import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { cn } from "@/lib/utils";
import { useAppStore } from "@/stores/app-store";
import type { BlockNoteEditor as Editor, PartialBlock } from "@blocknote/core";
import { BlockNoteEditor } from "@/features/editor/components/blocknote-editor";
import { maxSeq, pendingSegments, saveSegments } from "@/features/meetings/lib/transcript-store";
import { useMeetingAsr } from "@/features/meetings/lib/use-meeting-asr";
import { formatDuration, formatStartTime } from "@/features/meetings/utils/format";
import {
  clearSession,
  loadSession,
  saveSession,
  type MeetingSession,
} from "@/features/meetings/utils/session";
import { parseSpeakerLine } from "@/features/meetings/utils/transcript";
import type { SidecarToClient } from "@dp-work/contracts";

export function MeetingSessionPage() {
  const meetingTitle = useAppStore((s) => s.meetingTitle);
  const setMeetingStatus = useAppStore((s) => s.setMeetingStatus);
  const navigate = useNavigate();
  const [generating, setGenerating] = useState(false);
  const [endDialogOpen, setEndDialogOpen] = useState(false);
  // 结束会议时冻结的会议时长（秒）
  const [endedElapsed, setEndedElapsed] = useState<number | null>(null);

  // 会话状态：挂载时从 sessionStorage 恢复（重挂载不丢计时与转写）
  const [session, setSession] = useState<MeetingSession>(loadSession);

  // 每秒刷新当前时间，用于计算已进行时长
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (session.isPaused) return;
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [session.isPaused]);

  // 持久化会话状态
  useEffect(() => {
    saveSession(session);
  }, [session]);

  // 富文本编辑器实例：供 ASR 程序化插入 / 更新分句行
  const editorRef = useRef<Editor | null>(null);
  const onEditorReady = useCallback((e: Editor) => {
    editorRef.current = e;
  }, []);

  // ===== 本地实时保存（一分句一行，append-only；definite=true 事件统一走 saveSegments）=====
  const meetingId = meetingTitle ?? "unnamed";
  const seqRef = useRef(-1);
  const saveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [saveInfo, setSaveInfo] = useState({ saved: 0, pending: 0 });

  // 进入会议：从本地库恢复已保存行数与待同步队列
  useEffect(() => {
    let alive = true;
    maxSeq(meetingId).then((m) => {
      if (!alive) return;
      seqRef.current = m;
      if (m >= 0) setSaveInfo((s) => ({ ...s, saved: m + 1 }));
    });
    pendingSegments(meetingId).then((rows) => {
      if (!alive) return;
      setSaveInfo((s) => ({ ...s, pending: rows.length }));
    });
    return () => {
      alive = false;
    };
  }, [meetingId]);

  // ===== Sidecar ASR 对接：模拟分句流（definite=false 更新待定行 / definite=true 定型落库）=====
  // 待定行：文档末尾保留一个段落，ASR 中间结果实时填充；定型后在其上方插入正式行
  const pendingBlockIdRef = useRef<string | null>(null);

  const handleUtterance = useCallback(
    (u: Extract<SidecarToClient, { type: "utterance" }>) => {
      const editor = editorRef.current;
      if (!editor) return;
      if (u.definite) {
        // 定型分句：插入正式行（"发言人：内容"）+ 落本地库（pending）
        const text = u.speaker ? `${u.speaker}：${u.text}` : u.text;
        if (pendingBlockIdRef.current) {
          void editor.insertBlocks(
            [{ type: "paragraph", content: [{ type: "text", text, styles: {} }] }],
            pendingBlockIdRef.current,
            "before",
          );
          void editor.updateBlock(pendingBlockIdRef.current, { content: [] });
        } else {
          // 无待定行时追加到文档末尾（BlockNote 始终保留至少一个段落）
          const doc = editor.document;
          const anchor = doc[doc.length - 1]?.id ?? "";
          if (anchor) {
            void editor.insertBlocks(
              [{ type: "paragraph", content: [{ type: "text", text, styles: {} }] }],
              anchor,
              "after",
            );
          }
        }
        const seq = seqRef.current + 1;
        void saveSegments(
          meetingId,
          [
            {
              speaker: u.speaker ?? null,
              text: u.text,
              startMs: u.startMs ?? Date.now(),
            },
          ],
          seq,
        ).then((n) => {
          if (n > 0) {
            seqRef.current = seq;
            setSaveInfo((s) => ({ ...s, saved: s.saved + 1, pending: s.pending + 1 }));
          }
        });
      } else if (pendingBlockIdRef.current) {
        // 中间结果：更新待定行文本
        void editor.updateBlock(pendingBlockIdRef.current, {
          content: u.text ? [{ type: "text", text: u.text, styles: {} }] : [],
        });
      }
    },
    [meetingId],
  );

  const {
    status: asrStatus,
    start: startAsr,
    stop: stopAsr,
  } = useMeetingAsr(meetingId, handleUtterance);

  // 进入会议页：建立 WS 连接并登记 asr.start（编辑器就绪后取末尾段落作为待定行）
  useEffect(() => {
    const doc = editorRef.current?.document;
    if (!doc) return;
    const last = doc[doc.length - 1];
    if (last?.type === "paragraph") pendingBlockIdRef.current = last.id;
    if (asrStatus === "idle") startAsr();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [editorRef, meetingId, asrStatus]);

  // 解析编辑器行 → 分句（"发言人：内容" 或纯内容），防抖追加保存
  // 注：ASR 连接期间转写由 definite=true 事件统一落库，手动输入不再重复写入
  const persistToLocal = (doc: Record<string, unknown>[]) => {
    if (asrStatus === "live") return;
    const rows = (doc as { type?: string; content?: { text?: string }[] }[])
      .filter((b) => b.type === "paragraph" || b.type === "heading")
      .map((b) => parseSpeakerLine(b.content?.[0]?.text ?? "", Date.now()))
      .filter((r) => r.text.length > 0);
    if (saveTimerRef.current) clearTimeout(saveTimerRef.current);
    saveTimerRef.current = setTimeout(() => {
      if (rows.length <= seqRef.current + 1) return;
      const newOnes = rows.slice(seqRef.current + 1);
      saveSegments(meetingId, newOnes, seqRef.current + 1).then((n) => {
        seqRef.current += newOnes.length;
        setSaveInfo((s) => ({ ...s, saved: s.saved + n, pending: s.pending + n }));
      });
    }, 800);
  };

  const startTime = formatStartTime(session.startTs);
  const elapsed =
    session.pausedSec + (session.isPaused ? 0 : Math.floor((now - session.startTs) / 1000));
  // 会议结束后时长冻结在结束时刻
  const displayElapsed = asrStatus === "stopped" && endedElapsed !== null ? endedElapsed : elapsed;

  // 会议进行中阻止刷新 / 关闭 / 离开页面（F5、Ctrl+R、关闭标签页、切换路由等），防止转写内容丢失
  const allowLeaveRef = useRef(false);
  const blocker = useBlocker({
    // 显式开启浏览器级刷新/关闭拦截（F5、Ctrl+R、关标签页）
    enableBeforeUnload: true,
    shouldBlockFn: ({ current }) =>
      current.pathname === "/meetings/active" && !allowLeaveRef.current,
    withResolver: true,
  });

  useEffect(() => {
    if (blocker.status !== "blocked") return;
    const ok = window.confirm("会议进行中，离开将丢失实时转写内容，确定离开吗？");
    if (ok) blocker.proceed();
    else blocker.reset();
  }, [blocker]);

  return (
    <div className="flex h-full flex-col gap-4 px-6 py-5 md:px-8">
      {/* 顶部：返回 + 标题 + 状态 + 暂停 / 结束会议 */}
      <div className="flex items-center justify-between gap-3">
        <div className="flex min-w-0 items-center gap-3">
          <Button
            variant="ghost"
            size="icon"
            aria-label="返回会议列表"
            onClick={() => navigate({ to: "/meetings" })}
          >
            <ArrowLeft className="size-4" />
          </Button>
          <div className="flex min-w-0 flex-col">
            <h1 className="truncate text-lg font-semibold">{meetingTitle ?? "未命名会议"}</h1>
            <p className="text-muted-foreground text-xs">
              {startTime} 开始 · 已进行{" "}
              <span className="text-foreground font-medium tabular-nums">
                {formatDuration(displayElapsed)}
              </span>
              {saveInfo.saved > 0 && (
                <span className="ml-2">
                  · 已本地保存 <span className="text-foreground">{saveInfo.saved}</span> 条
                  {saveInfo.pending > 0 && <span> · 待同步 {saveInfo.pending}</span>}
                </span>
              )}
            </p>
          </div>
          <span
            className={cn(
              "flex shrink-0 items-center gap-1 rounded-full px-2 py-0.5 text-xs",
              asrStatus === "live"
                ? "bg-emerald-500/10 text-emerald-600"
                : asrStatus === "connecting"
                  ? "bg-sky-500/10 text-sky-600"
                  : "bg-zinc-500/10 text-zinc-500",
            )}
          >
            <span
              className={cn(
                "size-1.5 rounded-full bg-current",
                asrStatus === "live" && "animate-pulse",
              )}
            />
            {asrStatus === "live" ? "转写中" : asrStatus === "connecting" ? "连接中" : "未连接"}
          </span>
          <Button
            variant="ghost"
            size="icon"
            aria-label={
              asrStatus === "stopped" ? "开始转写" : session.isPaused ? "继续转写" : "暂停转写"
            }
            disabled={asrStatus === "stopped"}
            title={
              asrStatus === "stopped" ? "会议已结束" : session.isPaused ? "继续转写" : "暂停转写"
            }
            onClick={() =>
              setSession((s) => ({
                ...s,
                isPaused: !s.isPaused,
                pausedSec: s.isPaused
                  ? s.pausedSec
                  : s.pausedSec + Math.floor((Date.now() - s.startTs) / 1000),
              }))
            }
          >
            {session.isPaused || asrStatus === "stopped" ? (
              <Play className="size-4" />
            ) : (
              <Pause className="size-4" />
            )}
          </Button>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <Button
            size="sm"
            className="bg-black text-white hover:bg-black/90"
            disabled={asrStatus !== "stopped" || generating}
            title={asrStatus !== "stopped" ? "会议结束后才能生成会议纪要" : undefined}
            onClick={() => {
              // 生成会议纪要：调用占位接口，成功后回列表（列表展示「AI 会议纪要生成中」）
              setGenerating(true);
              const meetingId = meetingTitle ?? "unnamed";
              void fetch(
                `http://localhost:8000/api/v1/meetings/${encodeURIComponent(meetingId)}/minutes/generate`,
                {
                  method: "POST",
                  signal: AbortSignal.timeout(15000),
                },
              )
                .then(async (res) => {
                  if (!res.ok) throw new Error(`api 返回 ${res.status}`);
                  await res.json();
                  setMeetingStatus("generating");
                  navigate({ to: "/meetings" });
                })
                .catch(() => {
                  setGenerating(false);
                });
            }}
          >
            <Sparkles className="size-3.5" />
            {generating ? "正在生成…" : "生成会议纪要"}
          </Button>
          <Popover open={endDialogOpen} onOpenChange={(open) => setEndDialogOpen(open)}>
            <PopoverTrigger
              render={
                <Button
                  variant="outline"
                  size="sm"
                  disabled={asrStatus === "stopped" || generating}
                  title={asrStatus === "stopped" ? "会议已结束" : undefined}
                >
                  <Square className="size-3.5" />
                  {asrStatus === "stopped" ? "已结束" : "结束会议"}
                </Button>
              }
            />
            <PopoverContent align="end" className="w-64 p-3">
              <p className="text-sm font-medium">结束会议</p>
              <p className="text-muted-foreground mt-1 text-xs">
                结束将停止转写并清除本次会话内容，确定结束吗？
              </p>
              <div className="mt-3 flex justify-end gap-2">
                <Button variant="ghost" size="sm" onClick={() => setEndDialogOpen(false)}>
                  取消
                </Button>
                <Button
                  variant="destructive"
                  size="sm"
                  onClick={() => {
                    setEndDialogOpen(false);
                    // 结束会议：冻结时长 + 直接停止转写并清除会话，停留在当前页
                    setEndedElapsed(
                      session.pausedSec + Math.floor((Date.now() - session.startTs) / 1000),
                    );
                    stopAsr();
                    clearSession();
                    allowLeaveRef.current = true;
                  }}
                >
                  确定结束
                </Button>
              </div>
            </PopoverContent>
          </Popover>
        </div>
      </div>

      {/* 转写富文本（占满剩余区域），内容实时持久化 */}
      <section className="bg-card flex min-h-0 flex-1 flex-col rounded-xl border">
        <div className="min-h-0 flex-1 overflow-auto px-3 py-3">
          <BlockNoteEditor
            initialContent={
              (session.transcript as PartialBlock[] | undefined) ?? [
                { type: "paragraph", content: [] },
              ]
            }
            onEditorReady={onEditorReady}
            onChange={(blocks) => {
              setSession((s) => ({ ...s, transcript: blocks }));
              persistToLocal(blocks);
            }}
          />
        </div>
      </section>
    </div>
  );
}
