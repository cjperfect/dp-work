import { redirect } from "@tanstack/react-router";
import { useAuthStore, safeRedirect } from "@/stores/auth";
import type { AuthUser, CredentialErrors } from "@/types/auth";

/** 登录和注册均只检查必填项，不限制长度。 */
export function validateCredentials(username: string, password: string): CredentialErrors {
  const errors: CredentialErrors = {};
  if (!username.trim()) errors.username = "请输入用户名。";
  if (!password) errors.password = "请输入密码。";
  return errors;
}

/** 本地资料按用户数字主键隔离；字符串前缀仅用于存储键。 */
export function localAccountId(user: Pick<AuthUser, "id"> | null): string | null {
  if (!user || !Number.isSafeInteger(user.id) || user.id <= 0) return null;
  return `user:${user.id}`;
}

/** 已登录用户访问登录页时返回工作区。 */
export function redirectAuthenticatedUser(destination: unknown) {
  if (useAuthStore.getState().user)
    throw redirect({ href: safeRedirect(destination), replace: true });
}
