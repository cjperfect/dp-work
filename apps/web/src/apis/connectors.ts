import { request } from "@/lib/http";

export type FeishuAuthorization = {
  action: "configure" | "login";
  state: "starting" | "waiting" | "completed" | "failed" | "cancelled";
  url: string | null;
  qr_code: string | null;
  message: string | null;
  expires_at: string;
};
export type FeishuStatus = {
  installed: boolean;
  configured: boolean;
  connected: boolean;
  verified: boolean;
  account: string | null;
  last_verified_at: string | null;
  flow: FeishuAuthorization | null;
};

const BASE = "/api/connectors/feishu";
export function getFeishuStatus() {
  return request<FeishuStatus>(BASE);
}
export function startFeishuAuthorization(action: "configure" | "login") {
  return request<FeishuAuthorization>(`${BASE}/authorization/${action}`, { method: "POST" });
}
export function cancelFeishuAuthorization() {
  return request<null>(`${BASE}/authorization`, { method: "DELETE" });
}
export function verifyFeishuAuthorization() {
  return request<FeishuStatus>(`${BASE}/verify`, { method: "POST", timeout: 30000 });
}
export function disconnectFeishu() {
  return request<null>(`${BASE}/disconnect`, { method: "POST" });
}
