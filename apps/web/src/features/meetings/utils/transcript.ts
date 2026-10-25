/**
 * 会议模块工具：转写文本 / 数据解析（features/meetings/utils/transcript.ts）
 */

/** 分句 id = 幂等键（meetingId + seq 派生），与本地库 / 后端同步共用 */
export const segmentId = (meetingId: string, seq: number) => `${meetingId}#${seq}`;

/** 解析富文本行 → 分句："发言人：内容"（人名 ≤ 12 字符）或纯内容 */
export const parseSpeakerLine = (
  raw: string,
  now: number,
): { speaker: string | null; text: string; startMs: number } => {
  const trimmed = raw.trim();
  const m = trimmed.match(/^([^：:]{1,12})[：:]\s*(.+)/);
  return m
    ? { speaker: m[1], text: m[2], startMs: now }
    : { speaker: null, text: trimmed, startMs: now };
};

/** ArrayBuffer → Base64（WebSocket 发送 PCM 音频块用） */
export const arrayBufferToBase64 = (pcm: ArrayBuffer) => {
  const bytes = new Uint8Array(pcm);
  let bin = "";
  for (let i = 0; i < bytes.length; i += 1) bin += String.fromCharCode(bytes[i]);
  return btoa(bin);
};
