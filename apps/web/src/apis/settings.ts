import { request } from "@/lib/http";
import type {
  PersonalSettings,
  ServiceKind,
  ServiceInput,
  ConnectionResult,
} from "@/types/settings";

/** 读取当前账号的个人服务配置。 */
export function getSettings(): Promise<PersonalSettings> {
  return request("/api/settings");
}

/** 保存当前账号的服务配置。 */
export function saveService(kind: ServiceKind, data: ServiceInput): Promise<{ saved: boolean }> {
  return request(`/api/settings/${kind}`, { method: "PUT", data });
}

/** 测试表单中的服务配置，不自动保存。 */
export function testService(kind: ServiceKind, data: ServiceInput): Promise<ConnectionResult> {
  return request(`/api/settings/${kind}/test`, { method: "POST", data, timeout: 30000 });
}
