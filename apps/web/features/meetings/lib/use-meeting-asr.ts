/**
 * useMeetingAsr —— 会议页 ⇄ Sidecar 的 WebSocket 对接 hook。
 *
 * 开发期 Web 直连 sidecar（ws://localhost:8001/ws，跨端口 WS 不受 CORS 限制）；
 * 生产 Electron 场景改为经 Main 进程 IPC 转发（协议不变）。
 */
"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { ClientToSidecar, SidecarToClient } from "@dp-work/contracts";
import { SIDECAR_WS } from "@/features/meetings/constants/meeting";
import { arrayBufferToBase64 } from "@/features/meetings/utils/transcript";

export type AsrStatus = "idle" | "connecting" | "live" | "stopped";

export function useMeetingAsr(
  meetingId: string,
  onUtterance: (u: Extract<SidecarToClient, { type: "utterance" }>) => void,
) {
  const wsRef = useRef<WebSocket | null>(null);
  const [status, setStatus] = useState<AsrStatus>("idle");
  const onUtteranceRef = useRef(onUtterance);
  onUtteranceRef.current = onUtterance;

  const send = useCallback((msg: ClientToSidecar) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(msg));
    }
  }, []);

  const start = useCallback(() => {
    // 已有连接（含连接中）直接复用，避免 StrictMode 双调用重复建连导致 wsRef 被覆盖
    if (wsRef.current) return;
    setStatus("connecting");
    const ws = new WebSocket(SIDECAR_WS);
    wsRef.current = ws;
    ws.onopen = () => {
      // 仅当前连接可发 start/置 live：StrictMode 双挂载下旧连接回调可能晚触发
      if (wsRef.current !== ws) return;
      send({ type: "asr.start", meetingId });
      setStatus("live");
    };
    ws.onmessage = (e) => {
      if (wsRef.current !== ws) return;
      try {
        const msg = JSON.parse(e.data as string) as SidecarToClient;
        if (msg.type === "utterance") onUtteranceRef.current(msg);
      } catch {
        // 忽略无法解析的消息
      }
    };
    ws.onclose = () => {
      if (wsRef.current === ws) {
        setStatus("stopped");
        wsRef.current = null;
      }
    };
  }, [meetingId, send]);

  /** 发送 16kHz 单声道 PCM（ArrayBuffer）音频块 */
  const sendAudio = useCallback(
    (pcm: ArrayBuffer) => {
      send({ type: "audio", payload: arrayBufferToBase64(pcm) });
    },
    [send],
  );

  /** 停止转写：通知 sidecar + 立即断开 WS + 同步置状态（不等待 sidecar 关闭） */
  const stop = useCallback(() => {
    send({ type: "asr.stop", meetingId });
    wsRef.current?.close();
    wsRef.current = null;
    setStatus("stopped");
  }, [meetingId, send]);

  /** 硬关闭：立即断开 WS（页面卸载兜底） */
  const close = useCallback(() => {
    wsRef.current?.close();
    wsRef.current = null;
  }, []);

  // 卸载时关闭连接；同步置空 wsRef，避免 StrictMode 双挂载复用已死连接
  useEffect(
    () => () => {
      wsRef.current?.close();
      wsRef.current = null;
    },
    [],
  );

  return { status, start, stop, close, sendAudio };
}
