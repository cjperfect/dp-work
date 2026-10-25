import { HttpError, request, type RequestOptions } from "@/lib/http";
import { getAccessToken, useAuthStore } from "@/stores/auth";
import type {
  KnowledgeBaseInput,
  StoredKnowledgeBase,
} from "@/features/knowledge/lib/knowledge-repository";

type ServerKnowledgeBase = {
  id: number;
  owner_id: number;
  name: string;
  description: string;
  created_at: string;
  updated_at: string;
};

async function knowledgeRequest(accountId: string, path: string, init?: RequestOptions) {
  const user = useAuthStore.getState().user;
  const token = getAccessToken();
  if (!user || accountId !== `user:${user.id}` || !token)
    throw new Error("请先登录后再操作知识库。");
  let data: unknown;
  try {
    data = await request<unknown>(`/api/knowledge-bases${path}`, init);
  } catch (cause) {
    if (cause instanceof HttpError && cause.status === 401)
      throw new Error("登录已过期，请重新登录。", { cause });
    throw cause;
  }
  if (useAuthStore.getState().user?.id !== user.id || getAccessToken() !== token)
    throw new Error("登录状态已改变，请重试。");
  if (init?.method !== "DELETE" && data == null) throw new Error("服务返回的知识库数据无效。");
  return { data, user };
}

function toStoredKnowledgeBase(
  data: ServerKnowledgeBase,
  accountId: string,
  user: { id: number; username: string },
): StoredKnowledgeBase {
  if (
    !data ||
    !Number.isSafeInteger(data.id) ||
    data.id < 1 ||
    data.owner_id !== user.id ||
    [data.name, data.description, data.created_at, data.updated_at].some(
      (value) => typeof value !== "string",
    )
  )
    throw new Error("服务返回的知识库数据无效。");
  return {
    id: `server-${data.id}`,
    serverId: data.id,
    accountId,
    name: data.name,
    description: data.description,
    owner: user.username,
    files: [],
    documentCount: 0,
    createdAt: data.created_at,
    updatedAt: data.updated_at,
  };
}

export async function createKnowledgeBaseRequest(
  accountId: string,
  input: KnowledgeBaseInput,
): Promise<StoredKnowledgeBase> {
  const name = input.name.trim();
  if (!name) throw new Error("请输入知识库名称。");
  const { data, user } = await knowledgeRequest(accountId, "", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    data: { name, description: input.description.trim() },
  });
  return toStoredKnowledgeBase(data as ServerKnowledgeBase, accountId, user);
}

export type KnowledgeBasePage = {
  item: StoredKnowledgeBase[];
  total: number;
  page: number;
  page_size: number;
};

export async function listKnowledgeBasesRequest(
  accountId: string,
  q = "",
  page = 1,
  pageSize = 20,
): Promise<KnowledgeBasePage> {
  const query = new URLSearchParams({ page: String(page), page_size: String(pageSize) });
  if (q.trim()) query.set("q", q.trim());
  const { data, user } = await knowledgeRequest(accountId, `?${query}`, { method: "GET" });
  const pageData = data as Omit<KnowledgeBasePage, "item"> & { item: ServerKnowledgeBase[] };
  if (
    !pageData ||
    !Array.isArray(pageData.item) ||
    ![pageData.total, pageData.page, pageData.page_size].every(
      (value) => Number.isSafeInteger(value) && value >= 0,
    ) ||
    pageData.page !== page ||
    pageData.page_size !== pageSize
  )
    throw new Error("服务返回的知识库列表无效。");
  return {
    ...pageData,
    item: pageData.item.map((record: ServerKnowledgeBase) =>
      toStoredKnowledgeBase(record, accountId, user),
    ),
  };
}

export async function listAllKnowledgeBasesRequest(
  accountId: string,
): Promise<StoredKnowledgeBase[]> {
  const first = await listKnowledgeBasesRequest(accountId, "", 1, 100);
  const records = [...first.item];
  for (let page = 2; page <= Math.ceil(first.total / first.page_size); page += 1) {
    const result = await listKnowledgeBasesRequest(accountId, "", page, 100);
    records.push(...result.item);
  }
  return [...new Map(records.map((record) => [record.id, record])).values()];
}

function serverId(id: string): number {
  if (!/^server-[1-9]\d*$/.test(id)) throw new Error("此知识库尚未同步到服务器。");
  const value = Number(id.slice(7));
  if (!Number.isSafeInteger(value)) throw new Error("知识库 ID 无效。");
  return value;
}

export async function updateKnowledgeBaseRequest(
  accountId: string,
  id: string,
  input: KnowledgeBaseInput,
): Promise<StoredKnowledgeBase> {
  const name = input.name.trim();
  if (!name) throw new Error("请输入知识库名称。");
  const { data, user } = await knowledgeRequest(accountId, `/${serverId(id)}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    data: { name, description: input.description.trim() },
  });
  const record = toStoredKnowledgeBase(data as ServerKnowledgeBase, accountId, user);
  if (record.id !== id) throw new Error("服务返回的知识库数据无效。");
  return record;
}

export async function deleteKnowledgeBaseRequest(accountId: string, id: string): Promise<void> {
  await knowledgeRequest(accountId, `/${serverId(id)}`, { method: "DELETE" });
}
