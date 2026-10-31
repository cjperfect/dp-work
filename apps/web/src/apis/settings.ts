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

/** 读取当前账号的本机单价、任务预算及默认值。 */
export function getUsageSettings(): Promise<import("@/interfaces/settings").UsageSettings> {
  return http.get("/api/settings/usage");
}

/** 保存当前账号的本机单价与任务预算，后续任务生效。 */
export function saveUsageSettings(
  data: import("@/interfaces/settings").UsageSettingsInput,
): Promise<import("@/interfaces/settings").UsageSettings> {
  return http.put("/api/settings/usage", data);
}
