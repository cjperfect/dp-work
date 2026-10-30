import type {
  KnowledgeBasePage,
  KnowledgeBaseInput,
  StoredKnowledgeBase,
  ServerKnowledgeBase,
} from "@/interfaces/knowledge";
import { knowledgeRequest, serverId } from "./client";
import { toStoredKnowledgeBase } from "./mappers";

/** 创建知识库。 */
export async function createKnowledgeBaseRequest(
  accountId: string,
  input: KnowledgeBaseInput,
): Promise<StoredKnowledgeBase> {
  const name = input.name.trim();
  if (!name) throw new Error("请输入知识库名称。");
  const { data, user } = await knowledgeRequest.post(
    accountId,
    "",
    { name, description: input.description.trim() },
    { headers: { "Content-Type": "application/json" } },
  );
  return toStoredKnowledgeBase(data as ServerKnowledgeBase, accountId, user);
}

/** 分页查询知识库列表。 */
export async function listKnowledgeBasesRequest(
  accountId: string,
  q = "",
  page = 1,
  pageSize = 20,
): Promise<KnowledgeBasePage> {
  const query = new URLSearchParams({ page: String(page), page_size: String(pageSize) });
  if (q.trim()) query.set("q", q.trim());
  const { data, user } = await knowledgeRequest.get(accountId, `?${query}`);
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

/** 读取所有分页的知识库记录。 */
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

/** 修改知识库名称和描述。 */
export async function updateKnowledgeBaseRequest(
  accountId: string,
  id: string,
  input: KnowledgeBaseInput,
): Promise<StoredKnowledgeBase> {
  const name = input.name.trim();
  if (!name) throw new Error("请输入知识库名称。");
  const { data, user } = await knowledgeRequest.put(
    accountId,
    `/${serverId(id)}`,
    { name, description: input.description.trim() },
    { headers: { "Content-Type": "application/json" } },
  );
  const record = toStoredKnowledgeBase(data as ServerKnowledgeBase, accountId, user);
  if (record.id !== id) throw new Error("服务返回的知识库数据无效。");
  return record;
}

/** 删除指定知识库。 */
export async function deleteKnowledgeBaseRequest(accountId: string, id: string): Promise<void> {
  await knowledgeRequest.delete(accountId, `/${serverId(id)}`);
}
