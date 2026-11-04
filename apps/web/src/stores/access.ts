import { create } from "zustand";
import { getCurrentAccess } from "@/apis/access";
import { HttpError } from "@/lib/http";
import { getAccessToken, useAuthStore } from "@/stores/auth";
import type { CurrentAccess } from "@/interfaces/access";

interface AccessState {
  ownerId: number | null;
  data: CurrentAccess | null;
  error: string | null;
  loading: boolean;
}
export const useAccessStore = create<AccessState>(() => ({
  ownerId: null,
  data: null,
  error: null,
  loading: false,
}));
let revision = 0;
let pending: { token: string; owner: number; promise: Promise<CurrentAccess> } | null = null;

export function resetAccess() {
  revision += 1;
  pending = null;
  useAccessStore.setState({ ownerId: null, data: null, error: null, loading: false });
}
useAuthStore.subscribe((state, previous) => {
  if (state.user !== previous.user) resetAccess();
});

/** 合并同一会话的并发核验；账号切换后丢弃迟到结果。 */
export function refreshAccess(): Promise<CurrentAccess> {
  const owner = useAuthStore.getState().user?.id;
  const token = getAccessToken();
  if (!owner || !token) {
    resetAccess();
    return Promise.reject(new HttpError("请先登录。", 401));
  }
  if (pending?.token === token && pending.owner === owner) return pending.promise;
  const generation = revision;
  const current = () =>
    revision === generation &&
    getAccessToken() === token &&
    useAuthStore.getState().user?.id === owner;
  useAccessStore.setState({ ownerId: owner, loading: true, error: null });
  const promise = getCurrentAccess()
    .then((data) => {
      if (!current()) throw new HttpError("登录身份已变化，请重新进入。", 401);
      if (
        !data ||
        typeof data.role !== "string" ||
        !Array.isArray(data.permissions) ||
        data.permissions.some((p) => typeof p !== "string")
      )
        throw new Error("权限信息无效，请重试。");
      useAccessStore.setState({ ownerId: owner, data, error: null, loading: false });
      return data;
    })
    .catch((error: unknown) => {
      if (current())
        useAccessStore.setState({
          ownerId: owner,
          data: null,
          loading: false,
          error: error instanceof Error ? error.message : "权限加载失败。",
        });
      throw error;
    })
    .finally(() => {
      if (pending?.promise === promise) pending = null;
    });
  pending = { owner, token, promise };
  return promise;
}

export async function requireManagementAccess() {
  const data = await refreshAccess();
  if (!data.permissions.includes("access:manage"))
    throw new HttpError("当前账号没有用户与权限管理权限。", 403);
  return data;
}

/** 事件回调、延迟保存和卸载清理使用最新权限，避免闭包中的旧授权。 */
export function hasPermission(...permissions: string[]): boolean {
  const owner = useAuthStore.getState().user?.id;
  const state = useAccessStore.getState();
  return (
    !!owner &&
    state.ownerId === owner &&
    !!state.data &&
    permissions.every((permission) => state.data!.permissions.includes(permission))
  );
}

export async function requirePermissions(...permissions: string[]) {
  const data = await refreshAccess();
  if (!permissions.every((permission) => data.permissions.includes(permission)))
    throw new HttpError("当前账号没有此页面的访问权限。", 403);
  return data;
}
