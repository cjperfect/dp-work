/**
 * @dp-work/contracts —— IPC、JSON-RPC、事件的协议定义
 *
 * Web 前端、Electron Main、Sidecar（Python 侧按本文件对齐字段名）三方共用的
 * 转写/会议/同步协议类型。Sidecar WS 消息与 api 路由的入参出参均以这里为准。
 */

/** 转写分句（一分句一行，definite=true 定型） */
export interface TranscriptSegment {
  /** 分句 id = 幂等键（meetingId#seq，或服务端 UUID） */
  id: string;
  meetingId: string;
  /** 会议内序号（渲染/纪要排序） */
  seq: number;
  speaker: string | null;
  text: string;
  startMs: number | null;
  endMs: number | null;
}

/** 同步状态（本地 SQLite / IndexedDB 侧） */
export type SyncStatus = "pending" | "synced";

/** 本地存储的分句（带同步状态字段） */
export interface StoredSegment extends TranscriptSegment {
  syncStatus: SyncStatus;
  attempt: number;
  createdAt: number;
}

/* ============ Web ↔ Sidecar ASR 协议 ============ */

export interface AsrAudioFormat {
  format: "pcm";
  sampleRate: 16000;
  channels: 1;
  bitsPerSample: 16;
}

export interface AsrSegment {
  id: string;
  seq: number;
  revision: number;
  text: string;
  speakerId: string | null;
  startMs: number;
  endMs: number;
  isFinal: boolean;
}

export interface WsAsrStart {
  type: "asr.start";
  requestId: string;
  meetingId: string;
  audio: AsrAudioFormat;
  nextSeq: number;
  offsetMs: number;
}

export interface WsAsrStop {
  type: "asr.stop";
  requestId: string;
  meetingId: string;
}

export interface WsAsrReady {
  type: "asr.ready";
  requestId: string;
  meetingId: string;
  sessionId: string;
}

/** isFinal=true 表示 ASR 确认；客户端仍需调用 API 保存。 */
export interface WsAsrTranscript {
  type: "asr.transcript";
  meetingId: string;
  sessionId: string;
  segment: AsrSegment;
}

export interface WsAsrStopped {
  type: "asr.stopped";
  requestId: string;
  meetingId: string;
  sessionId: string;
  lastFinalSeq: number;
}

export interface WsAsrError {
  type: "asr.error";
  requestId?: string;
  meetingId?: string;
  code: string;
  message: string;
  retryable: boolean;
}

/** 音频通过独立的二进制 WebSocket 帧发送，PCM16 小端，建议每帧 200ms。 */
export type ClientToSidecar = WsAsrStart | WsAsrStop;
export type SidecarToClient = WsAsrReady | WsAsrTranscript | WsAsrStopped | WsAsrError;

/* ============ api 服务（POST /api/segments） ============ */

export interface SegmentInput {
  id?: string;
  seq: number;
  speaker?: string | null;
  text: string;
  startMs?: number | null;
  endMs?: number | null;
}

export interface SegmentsBatch {
  meetingId: string;
  segments: SegmentInput[];
}

export interface SegmentsBatchResult {
  written: number;
  ignored: number;
}

/** Sidecar → api 上行协议常量（字段名与 Python 端对齐） */
export const SYNC_API = {
  /** 批量上行端点 */
  segmentsPath: "/api/segments",
  /** 每批最大分句数 */
  batchSize: 200,
} as const;

export type { DesktopInfo, DesktopBridge } from "./desktop";
