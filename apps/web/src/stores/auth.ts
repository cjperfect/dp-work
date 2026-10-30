import type { AuthMode, AuthUser } from "@/interfaces/auth";
import { create } from "zustand";
import { onUnauthorized } from "@/lib/http";
import { getEncryptionKey, submitCredentials } from "@/apis/auth";
import { getStoredToken, TOKEN_KEY } from "@/lib/token-storage";
import { encryptPassword } from "@/features/auth/lib/password-encryption";

export type { AuthUser } from "@/interfaces/auth";
const USER_KEY = "dp-work.auth.user";
// 防止退出后，仍在进行的登录重新写入旧身份。
let sessionRevision = 0;

export const useAuthStore = create<{ user: AuthUser | null }>(() => ({ user: null }));

export function getAccessToken(): string | null {
  return getStoredToken();
}

function readCachedUser(): AuthUser | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = localStorage.getItem(USER_KEY);
    if (!raw) return null;
    const user = JSON.parse(raw) as AuthUser;
    return typeof user?.id === "number" && typeof user?.username === "string" ? user : null;
  } catch {
    return null;
  }
}

function writeCachedUser(user: AuthUser | null) {
  if (typeof window === "undefined") return;
  try {
    if (user) localStorage.setItem(USER_KEY, JSON.stringify(user));
    else localStorage.removeItem(USER_KEY);
  } catch {
    // 存储受限时仅保留内存身份。
  }
}

export function signOut() {
  sessionRevision += 1;
  try {
    if (typeof window !== "undefined") localStorage.removeItem(TOKEN_KEY);
  } catch {
    // 存储受限时仍清除当前页面身份。
  }
  writeCachedUser(null);
  useAuthStore.setState({ user: null });
}

onUnauthorized((token) => {
  if (getAccessToken() === token) signOut();
});

export async function authenticate(
  mode: AuthMode,
  username: string,
  password: string,
  department?: string,
) {
  const revision = ++sessionRevision;
  const normalizedUsername = username.trim();
  const publicKey = await getEncryptionKey();
  if (revision !== sessionRevision) throw new Error("登录操作已取消，请重试。");
  const encryptedPassword = await encryptPassword(publicKey, normalizedUsername, password, mode);
  if (revision !== sessionRevision) throw new Error("登录操作已取消，请重试。");
  const payload: Record<string, string> = {
    username: normalizedUsername,
    encrypted_password: encryptedPassword,
  };
  if (mode === "register" && department) payload.department = department;
  const session = await submitCredentials(mode, payload);
  if (revision !== sessionRevision) throw new Error("登录操作已取消，请重试。");
  // 仅持久化令牌，不保存密码。
  try {
    localStorage.setItem(TOKEN_KEY, session.token);
  } catch {
    throw new Error("浏览器无法保存登录状态，请允许站点存储后重试。");
  }
  // 缓存登录接口返回的用户信息。
  writeCachedUser(session.user);
  useAuthStore.setState({ user: session.user });
}

export function restoreAuthSession(): AuthUser | null {
  const user = getAccessToken() ? readCachedUser() : null;
  useAuthStore.setState({ user });
  return user;
}

/** 仅允许站内地址，避免登录后跳转到外部网站或再次进入认证页。 */
export function safeRedirect(value: unknown): string {
  if (
    typeof value !== "string" ||
    !value.startsWith("/") ||
    value.startsWith("//") ||
    value.includes("\\")
  )
    return "/";
  try {
    const url = new URL(value, "https://dp-work.invalid");
    if (url.origin !== "https://dp-work.invalid" || /^\/sign-(in|up)(\/|$)/.test(url.pathname))
      return "/";
    return url.pathname + url.search + url.hash;
  } catch {
    return "/";
  }
}
