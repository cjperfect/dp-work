/**
 * 会议模块工具：会话持久化（features/meetings/utils/session.ts）
 *
 * 会议会话状态持久化到 sessionStorage，页面意外重挂载 / 刷新后完整恢复。
 */
import { SESSION_KEY } from "@/constants/meeting";

/** 会议会话状态：持久化到 sessionStorage，页面意外重挂载 / 刷新后完整恢复 */
export type MeetingSession = {
  startTs: number;
  pausedSec: number;
  isPaused: boolean;
  /** BlockNote 文档 blocks（JSON 序列化） */
  transcript: Record<string, unknown>[] | null;
};

export const loadSession = (): MeetingSession => {
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

export const saveSession = (session: MeetingSession) => {
  try {
    sessionStorage.setItem(SESSION_KEY, JSON.stringify(session));
  } catch {
    // 存储不可用时忽略
  }
};

export const clearSession = () => {
  try {
    sessionStorage.removeItem(SESSION_KEY);
  } catch {
    // 忽略
  }
};
