import { create } from "zustand";

export type AuthUser = {
  id: string;
  username: string;
  display_name: string;
  department: string;
  role: string;
  status: number;
};

type AuthSession = { token: string; user: AuthUser };
const TOKEN_KEY = "dp-work.auth.token";

export const useAuthStore = create<{ user: AuthUser | null }>(() => ({ user: null }));

function readToken(): string | null {
  if (typeof window === "undefined") return null;
  try {
    return sessionStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function signOut() {
  if (typeof window !== "undefined") sessionStorage.removeItem(TOKEN_KEY);
  useAuthStore.setState({ user: null });
}

class AuthError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
  }
}

async function authRequest<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`/api/v1/auth${path}`, {
      ...init,
      signal: AbortSignal.timeout(15_000),
      headers: { "Content-Type": "application/json", ...init?.headers },
    });
  } catch {
    throw new Error("暂时无法连接服务，请稍后重试。");
  }
  const body = await response.json().catch(() => null);
  if (!response.ok || body?.code !== 0 || !body?.data) {
    throw new AuthError(body?.message ?? "服务暂时不可用，请稍后重试。", response.status);
  }
  return body.data as T;
}

export async function authenticate(mode: "login" | "register", username: string, password: string) {
  const session = await authRequest<AuthSession>(`/${mode}`, {
    method: "POST",
    body: JSON.stringify({ username: username.trim(), password }),
  });
  // 仅保存令牌，不保存密码；关闭当前标签页后结束本地会话。
  sessionStorage.setItem(TOKEN_KEY, session.token);
  useAuthStore.setState({ user: session.user });
}

export async function restoreAuthSession(): Promise<AuthUser | null> {
  const token = readToken();
  if (!token) return null;
  try {
    const user = await authRequest<AuthUser>("/users/me", {
      headers: { Authorization: `Bearer ${token}` },
    });
    useAuthStore.setState({ user });
    return user;
  } catch (error) {
    if (error instanceof AuthError && (error.status === 401 || error.status === 403)) {
      signOut();
      return null;
    }
    throw error;
  }
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
