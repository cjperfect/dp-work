import { HttpError, http } from "@/lib/http";
import { getAccessToken, useAuthStore } from "@/stores/auth";

/** 校验知识库请求所属账号及返回数据。 */
async function guardedKnowledgeRequest(
  accountId: string,
  execute: () => Promise<unknown>,
  allowEmpty = false,
) {
  const user = useAuthStore.getState().user;
  const token = getAccessToken();
  if (!user || accountId !== `user:${user.id}` || !token)
    throw new Error("请先登录后再操作知识库。");
  let data: unknown;
  try {
    data = await execute();
  } catch (cause) {
    if (cause instanceof HttpError && cause.status === 401)
      throw new Error("登录已过期，请重新登录。", { cause });
    throw cause;
  }
  if (useAuthStore.getState().user?.id !== user.id || getAccessToken() !== token)
    throw new Error("登录状态已改变，请重试。");
  if (!allowEmpty && data == null) throw new Error("服务返回的知识库数据无效。");
  return { data, user };
}

type Options = Parameters<typeof http.get>[1];
/** 构造知识库接口地址。 */
const endpoint = (path: string) => `/api/knowledge-bases${path}`;

export const knowledgeRequest = {
  /** 发送查询请求并校验当前账号。 */
  get: (account: string, path: string, options?: Options) =>
    guardedKnowledgeRequest(account, () => http.get(endpoint(path), options)),
  /** 发送新增或执行请求并校验当前账号。 */
  post: (account: string, path: string, data?: unknown, options?: Options) =>
    guardedKnowledgeRequest(account, () => http.post(endpoint(path), data, options)),
  /** 发送更新请求并校验当前账号。 */
  put: (account: string, path: string, data?: unknown, options?: Options) =>
    guardedKnowledgeRequest(account, () => http.put(endpoint(path), data, options)),
  /** 发送局部更新请求并校验当前账号。 */
  patch: (account: string, path: string, data?: unknown, options?: Options) =>
    guardedKnowledgeRequest(account, () => http.patch(endpoint(path), data, options)),
  /** 发送删除请求并校验当前账号。 */
  delete: (account: string, path: string, options?: Options) =>
    guardedKnowledgeRequest(account, () => http.delete(endpoint(path), options), true),
};

/** 校验并转换知识库服务端 ID。 */
export function serverId(id: string): number {
  if (!/^server-[1-9]\d*$/.test(id)) throw new Error("此知识库尚未同步到服务器。");
  const value = Number(id.slice(7));
  if (!Number.isSafeInteger(value)) throw new Error("知识库 ID 无效。");
  return value;
}
