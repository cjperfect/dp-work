import { useCallback, useEffect, useRef, useState } from "react";
import type { WsAsrTranscript, WsAsrSync } from "@dp-work/contracts";
import { SIDECAR_WS } from "@/features/meetings/constants/meeting";
import { AsrClient, type AsrStatus } from "../lib/asr-client";

/** 管理会议页与 Sidecar 的实时转写连接。 */
export function useMeetingAsr(
  meetingId: string,
  onTranscript: (message: WsAsrTranscript) => unknown | Promise<unknown>,
) {
  const client = useRef<AsrClient | null>(null);
  const callback = useRef(onTranscript);
  callback.current = onTranscript;
  const [status, setStatus] = useState<AsrStatus>("idle");
  const [error, setError] = useState<string | null>(null);
  const [sync, setSync] = useState<WsAsrSync | null>(null);
  useEffect(() => {
    const current = new AsrClient(meetingId, SIDECAR_WS, {
      onTranscript: (message) => callback.current(message),
      onStatus: setStatus,
      onError: setError,
      onSync: setSync,
    });
    client.current = current;
    setStatus("idle");
    setError(null);
    setSync(null);
    return () => {
      client.current = null;
      current.close();
    };
  }, [meetingId]);
  const start = useCallback(async () => {
    setError(null);
    if (!client.current) throw new Error("转写连接尚未初始化。");
    await client.current.start();
  }, []);
  const stop = useCallback(() => client.current?.stop() ?? Promise.resolve(), []);
  const close = useCallback(() => client.current?.close(), []);
  const sendAudio = useCallback((pcm: ArrayBuffer) => client.current?.sendAudio(pcm) ?? false, []);
  return { status, error, sync, start, stop, close, sendAudio };
}
