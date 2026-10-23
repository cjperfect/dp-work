"use client";

import "@blocknote/core/fonts/inter.css";
import "@blocknote/mantine/style.css";

import { useCreateBlockNote } from "@blocknote/react";
import { BlockNoteView } from "@blocknote/mantine";
import { ArrowLeft, Pause, Play, Square } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useNavigate, useBlocker } from "@tanstack/react-router";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { useAppStore } from "@/stores/app-store";
import { zh } from "@blocknote/core/locales";
import {
  clearMeeting,
  maxSeq,
  pendingSegments,
  saveSegments,
} from "@/features/meetings/lib/transcript-store";

const formatDuration = (total: number) =>
  [Math.floor(total / 3600), Math.floor(total / 60) % 60, total % 60]
    .map((n) => String(n).padStart(2, "0"))
    .join(":");

/** 会议会话状态：持久化到 sessionStorage，页面意外重挂载 / 刷新后完整恢复 */
type MeetingSession = {
  startTs: number;
  pausedSec: number;
  isPaused: boolean;
  /** BlockNote 文档 blocks（JSON 序列化） */
  transcript: Record<string, unknown>[] | null;
};

const SESSION_KEY = "dp-meeting-session-v1";

const loadSession = (): MeetingSession => {
  try {
    const raw = sessionStorage.getItem(SESSION_KEY);
    if (raw) {
      const parsed = JSON.parse(raw) as MeetingSession;
      if (typeof parsed.startTs === "number") return parsed;
    }
  } catch {
    // 忽略损坏数据，按新会议处理
  }
  return { startTs: Date.now(), pausedSec: 0, isPaused: false, transcript: null };
};

export function MeetingSessionPage() {
  const meetingTitle = useAppStore((s) => s.meetingTitle);
  const setMeetingStatus = useAppStore((s) => s.setMeetingStatus);
  const navigate = useNavigate();

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
    try {
      sessionStorage.setItem(SESSION_KEY, JSON.stringify(session));
    } catch {
      // 存储不可用时忽略
    }
  }, [session]);

  const editor = useCreateBlockNote({
    dictionary: zh,
    // 从持久化状态恢复转写内容
    ...(session.transcript ? { initialContent: session.transcript } : {}),
    // 扩展文字颜色样式（默认样式仅含背景色，无前景色）
    styleSchema: {
      color: {
        type: "string",
        default: "#000000",
        propSchema: "string",
      },
    },
  });

  // ===== 本地实时保存（一分句一行，append-only；未来 definite=true 事件直接走 saveSegments）=====
  const meetingId = meetingTitle ?? "unnamed";
  const seqRef = useRef(-1);
  const savedCountRef = useRef(0);
  const saveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [saveInfo, setSaveInfo] = useState({ saved: 0, pending: 0 });

  // 进入会议：从本地库恢复已保存行数与待同步队列
  useEffect(() => {
    let alive = true;
    maxSeq(meetingId).then((m) => {
      if (!alive) return;
      seqRef.current = m;
    });
    pendingSegments(meetingId).then((rows) => {
      if (!alive) return;
      setSaveInfo((s) => ({ ...s, pending: rows.length }));
    });
    return () => {
      alive = false;
    };
  }, [meetingId]);

  // 解析编辑器行 → 分句（"发言人：内容" 或纯内容），防抖追加保存
  const persistToLocal = (doc: Record<string, unknown>[]) => {
    const rows = (doc as { type?: string; content?: { text?: string }[] }[])
      .filter((b) => b.type === "paragraph" || b.type === "heading")
      .map((b) => {
        const raw = (b.content?.[0]?.text ?? "").trim();
        const m = raw.match(/^([^：:]{1,12})[：:]\s*(.+)/);
        return m ? { speaker: m[1], text: m[2] } : { speaker: null, text: raw };
      })
      .filter((r) => r.text.length > 0);
    if (saveTimerRef.current) clearTimeout(saveTimerRef.current);
    saveTimerRef.current = setTimeout(() => {
      if (rows.length <= savedCountRef.current) return;
      const newOnes = rows.slice(savedCountRef.current);
      saveSegments(meetingId, newOnes, seqRef.current + 1).then((n) => {
        seqRef.current += newOnes.length;
        savedCountRef.current = rows.length;
        setSaveInfo((s) => ({ ...s, saved: savedCountRef.current, pending: s.pending + n }));
      });
    }, 800);
  };

  const startTime = new Date(session.startTs).toLocaleTimeString("zh-CN", {
    hour: "2-digit",
    minute: "2-digit",
  });
  const elapsed =
    session.pausedSec + (session.isPaused ? 0 : Math.floor((now - session.startTs) / 1000));

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
                {formatDuration(elapsed)}
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
              session.isPaused
                ? "bg-amber-500/10 text-amber-600"
                : "bg-emerald-500/10 text-emerald-600",
            )}
          >
            <span
              className={cn(
                "size-1.5 rounded-full bg-current",
                !session.isPaused && "animate-pulse",
              )}
            />
            {session.isPaused ? "已暂停" : "转写中"}
          </span>
          <Button
            variant="ghost"
            size="icon"
            aria-label={session.isPaused ? "继续转写" : "暂停转写"}
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
            {session.isPaused ? <Play className="size-4" /> : <Pause className="size-4" />}
          </Button>
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={() => {
            // 结束会议：清除会话持久化，放行拦截（正常结束流程），标记为「AI 纪要生成中」，回到会议列表页
            try {
              sessionStorage.removeItem(SESSION_KEY);
            } catch {
              // 忽略
            }
            allowLeaveRef.current = true;
            setMeetingStatus("generating");
            navigate({ to: "/meetings" });
          }}
        >
          <Square className="size-3.5" />
          结束会议
        </Button>
      </div>

      {/* 转写富文本（占满剩余区域），内容实时持久化 */}
      <section className="bg-card flex min-h-0 flex-1 flex-col rounded-xl border">
        <div className="min-h-0 flex-1 overflow-auto px-3 py-3">
          <BlockNoteView
            editor={editor}
            theme="light"
            onChange={(ed) => {
              setSession((s) => ({
                ...s,
                transcript: ed.document as unknown as Record<string, unknown>[],
              }));
              persistToLocal(ed.document as unknown as Record<string, unknown>[]);
            }}
          />
        </div>
      </section>
    </div>
  );
}
