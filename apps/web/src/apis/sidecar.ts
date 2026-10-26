import { request } from "@/lib/http";

/** 检查当前用户实际生效的转写配置。 */
export function getSidecarAsrConfig(): Promise<{ configured: boolean }> {
  return request("/api/settings/asr/configured");
}

/** 获取短时连接票据；API Key 仅在 API 和 Sidecar 之间传递。 */
export function createAsrSession(meetingId: string): Promise<{ ticket: string }> {
  return request(`/api/settings/asr/session/${encodeURIComponent(meetingId)}`, { method: "POST" });
}
