import { useCallback, useEffect, useRef, useState } from "react";
import type { WsAsrTranscript, WsAsrSync } from "@dp-work/contracts";
import { getSidecarAsrConfig } from "@/apis/sidecar";
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
  const [sync, setSync] = useState<WsAsrSync | null>(null);
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
      onSync: (value) => {
        if (alive) setSync(value);
      },
    });
    client.current = current;
    setStatus("idle");
    setError(null);
    setSync(null);
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
        throw new Error("豆包 ASR 凭证尚未配置，请填写 Sidecar .env 后重启服务。");
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
      await current.start();
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
  }, []);

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
  return { status, error, sync, start, stop, close };
}
