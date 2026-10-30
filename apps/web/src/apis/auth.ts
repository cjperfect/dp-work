import type { AuthMode, AuthSession, PasswordEncryptionKey } from "@/interfaces/auth";
import { HttpError, http } from "@/lib/http";

/** 请求认证接口。 */
async function authRequest<T>(execute: () => Promise<T>): Promise<T> {
  const data = await execute();
  if (data == null) throw new HttpError("服务暂时不可用，请稍后重试。", 500);
  return data;
}

/** 获取密码加密公钥。 */
export function getEncryptionKey(): Promise<PasswordEncryptionKey> {
  return authRequest(() =>
    http.get<PasswordEncryptionKey>("/api/auth/encryption-key", { auth: false }),
  );
}

/** 提交登录或注册信息。 */
export function submitCredentials(
  mode: AuthMode,
  payload: Record<string, string>,
): Promise<AuthSession> {
  return authRequest(() => http.post<AuthSession>(`/api/auth/${mode}`, payload, { auth: false }));
}
