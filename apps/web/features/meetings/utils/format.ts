/**
 * 会议模块工具：时间 / 文本格式化（features/meetings/utils/format.ts）
 */

/** 秒 → HH:MM:SS（会议计时、ASR 时间轴共用） */
export const formatDuration = (total: number) =>
  [Math.floor(total / 3600), Math.floor(total / 60) % 60, total % 60]
    .map((n) => String(n).padStart(2, "0"))
    .join(":");

/** 时间戳 → 本地 HH:mm（会议开始时间展示） */
export const formatStartTime = (ts: number) =>
  new Date(ts).toLocaleTimeString("zh-CN", {
    hour: "2-digit",
    minute: "2-digit",
  });
