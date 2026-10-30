import type { FeishuAuthorization, FeishuStatus } from "@/interfaces/connectors";
import { http } from "@/lib/http";

const BASE = "/api/connectors/feishu";
/** 获取当前账号的飞书授权状态。 */
export function getFeishuStatus() {
  return http.get<FeishuStatus>(BASE);
}
/** 发起飞书应用配置或用户授权。 */
export function startFeishuAuthorization(action: "configure" | "login") {
  return http.post<FeishuAuthorization>(`${BASE}/authorization/${action}`);
}
/** 取消当前飞书授权流程。 */
export function cancelFeishuAuthorization() {
  return http.delete<null>(`${BASE}/authorization`);
}
/** 验证飞书用户授权是否有效。 */
export function verifyFeishuAuthorization() {
  return http.post<FeishuStatus>(`${BASE}/verify`, undefined, { timeout: 30000 });
}
/** 退出当前账号的飞书连接。 */
export function disconnectFeishu() {
  return http.post<null>(`${BASE}/disconnect`);
}
