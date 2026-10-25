import { HttpError, request, type RequestOptions } from "@/lib/http";
import type { AuthMode, AuthSession, PasswordEncryptionKey } from "@/types/auth";

/** 请求认证接口。 */
async function authRequest<T>(path: string, init?: RequestOptions): Promise<T> {
  const data = await request<T>(`/api/auth${path}`, { ...init, auth: false });
  if (data == null) throw new HttpError("服务暂时不可用，请稍后重试。", 500);
  return data;
}

/** 获取密码加密公钥。 */
export function getEncryptionKey(): Promise<PasswordEncryptionKey> {
  return authRequest("/encryption-key");
}

/** 提交登录或注册信息。 */
export function submitCredentials(
  mode: AuthMode,
  payload: Record<string, string>,
): Promise<AuthSession> {
  return authRequest(`/${mode}`, { method: "POST", data: payload });
}
