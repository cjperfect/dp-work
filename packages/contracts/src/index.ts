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

/* ============ Sidecar WebSocket 消息（JSON-RPC 风格） ============ */

export interface WsReady {
  type: "ready";
  meetingId: string;
}

/** 分句事件：definite=false 为中间结果（前端更新当前行，不落库）；true 为定型（已落库 pending） */
export interface WsUtterance {
  type: "utterance";
  definite: boolean;
  seq?: number;
  text: string;
  speaker?: string | null;
  startMs?: number;
  endMs?: number;
}

export interface WsAudioAck {
  type: "audio.ack";
  bytes: number;
}

export interface WsStopped {
  type: "stopped";
  meetingId: string | null;
}

export type SidecarToClient = WsReady | WsUtterance | WsAudioAck | WsStopped;

/* ============ 客户端 → Sidecar ============ */

export interface WsAsrStart {
  type: "asr.start";
  meetingId: string;
  sampleRate?: number;
}

export interface WsAudio {
  type: "audio";
  /** base64 PCM */
  payload: string;
}

export interface WsAsrStop {
  type: "asr.stop";
  meetingId: string;
}

export type ClientToSidecar = WsAsrStart | WsAudio | WsAsrStop;

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
