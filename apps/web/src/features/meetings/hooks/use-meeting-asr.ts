import { useCallback, useEffect, useRef, useState } from "react";
import type { WsAsrTranscript } from "@dp-work/protocols/asr";
import { getMeeting, elapsed } from "@/apis/meetings";
import { useAuthStore } from "@/stores/auth";
import { getSidecarAsrConfig, createAsrSession } from "@/apis/sidecar";
import { SIDECAR_WS } from "@/features/meetings/constants/meeting";
import { AsrClient, type AsrStatus } from "../lib/asr-client";
import { PcmRecorder } from "../lib/pcm-recorder";

/** 管理麦克风、Sidecar 连接和转写收尾。 */
export function useMeetingAsr(
  meetingId: string,
  onTranscript: (message: WsAsrTranscript) => unknown | Promise<unknown>,
) {
  const client = useRef<AsrClient | null>(null);
  const recorder = useRef<PcmRecorder | null>(null);
  const revision = useRef(0);
  const callback = useRef(onTranscript);
  callback.current = onTranscript;
  const [status, setStatus] = useState<AsrStatus>("idle");
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let alive = true;
    const current = new AsrClient(meetingId, SIDECAR_WS, {
      onTranscript: (message) => callback.current(message),
      onStatus: (value) => {
        if (alive) setStatus(value);
      },
      onError: (message) => {
        recorder.current?.close();
        recorder.current = null;
        if (alive) setError(message);
      },
    });
    client.current = current;
    setStatus("idle");
    setError(null);
    return () => {
      alive = false;
      recorder.current?.close();
      recorder.current = null;
      client.current = null;
      current.close();
    };
  }, [meetingId]);

  const start = useCallback(async () => {
    const current = client.current;
    if (!current) throw new Error("转写连接尚未初始化。");
    const generation = ++revision.current;
    const active = () => generation === revision.current && client.current === current;
    let capture: PcmRecorder | null = null;
    setError(null);
    setStatus("connecting");
    try {
      const config = await getSidecarAsrConfig();
      if (!active()) return;
      if (!config.configured)
        throw new Error("豆包 ASR 凭证尚未配置，请前往设置中的会议转写填写。");
      const owner = useAuthStore.getState().user?.id;
      if (!owner) throw new Error("请先登录。");
      const workspace = await getMeeting(owner, meetingId);
      if (!active()) return;
      if (!workspace || workspace.meeting.status !== "active")
        throw new Error("会议不存在或尚未恢复，请重新加载后重试。");
      const nextSeq = workspace.segments.reduce((next, row) => Math.max(next, row.seq + 1), 0);
      const lastEnd = workspace.segments.reduce(
        (end, row) => Math.max(end, row.end_ms ?? row.start_ms),
        0,
      );
      capture = new PcmRecorder(
        (chunk) => current.sendAudio(chunk),
        (cause) => {
          if (!active()) return;
          capture?.close();
          recorder.current = null;
          current.close();
          setError(cause.message);
          setStatus("error");
        },
      );
      recorder.current = capture;
      await capture.prepare();
      if (!active()) {
        capture?.close();
        return;
      }
      const { ticket } = await createAsrSession(meetingId);
      if (!active()) {
        capture?.close();
        return;
      }
      await current.start({
        ticket,
        nextSeq,
        offsetMs: Math.max(lastEnd, Math.floor(elapsed(workspace.meeting))),
      });
      if (!active()) {
        capture?.close();
        return;
      }
      capture?.start();
    } catch (cause) {
      capture?.close();
      if (!active()) return;
      recorder.current = null;
      current.close();
      const message = cause instanceof Error ? cause.message : "启动转写失败。";
      setError(message);
      setStatus("error");
      throw cause;
    }
  }, [meetingId]);

  const stop = useCallback(async () => {
    revision.current++;
    const capture = recorder.current;
    recorder.current = null;
    try {
      // 麦克风尾帧先发送，再提交 asr.stop，避免丢失最后一句。
      await capture?.stop();
      await client.current?.stop();
      setStatus("stopped");
    } catch (cause) {
      client.current?.close();
      setError(cause instanceof Error ? cause.message : "停止转写失败。");
      setStatus("error");
      throw cause;
    }
  }, []);
  const close = useCallback(() => {
    revision.current++;
    recorder.current?.close();
    recorder.current = null;
    client.current?.close();
  }, []);
  return { status, error, start, stop, close };
}
