/** Web 与 Sidecar 之间的 ASR WebSocket 协议。 */
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
  /** 短时一次性连接票据；不包含上游密钥。 */
  ticket?: string;
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
