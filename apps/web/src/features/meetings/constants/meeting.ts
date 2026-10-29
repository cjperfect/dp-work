/**
 * 会议模块常量（features/meetings/constants/meeting.ts）
 */

/** 会议会话持久化键（sessionStorage）——创建/恢复/清除三处共用 */
export const SESSION_KEY = "dp-meeting-session-v1";

/** 本机 Sidecar WebSocket 地址。 */
export const SIDECAR_WS = import.meta.env.VITE_SIDECAR_WS ?? "ws://localhost:8001/ws";
