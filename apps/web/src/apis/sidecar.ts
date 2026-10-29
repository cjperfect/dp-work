import { request } from "@/lib/http";

/** 检查当前用户实际生效的转写配置。 */
export function getSidecarAsrConfig(): Promise<{ configured: boolean }> {
  return request("/api/settings/asr/configured");
}

/** 获取短时连接票据；API Key 由本机 Sidecar 读取，不经过云端 API。 */
export function createAsrSession(meetingId: string): Promise<{ ticket: string }> {
  return request(`/api/meetings/${encodeURIComponent(meetingId)}/asr/session`, { method: "POST" });
}
