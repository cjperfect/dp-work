import type {
  PersonalSettings,
  ServiceKind,
  ServiceInput,
  ConnectionResult,
} from "@/interfaces/settings";
import { http } from "@/lib/http";

/** 读取当前账号的个人服务配置。 */
export function getSettings(): Promise<PersonalSettings> {
  return http.get("/api/settings");
}

/** 保存当前账号的服务配置。 */
export function saveService(kind: ServiceKind, data: ServiceInput): Promise<{ saved: boolean }> {
  return http.put(`/api/settings/${kind}`, data);
}

/** 测试表单中的服务配置，不自动保存。 */
export function testService(kind: ServiceKind, data: ServiceInput): Promise<ConnectionResult> {
  return http.post(`/api/settings/${kind}/test`, data, { timeout: 30000 });
}
