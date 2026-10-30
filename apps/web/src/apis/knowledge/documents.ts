import type { KbFile, EditorDocumentInput, ServerKnowledgeDocument } from "@/interfaces/knowledge";
import { knowledgeRequest, serverId } from "./client";
import { toKnowledgeDocument } from "./mappers";

/** 保存在线文档标题、正文和富文本结构。 */
export async function saveKnowledgeDocumentRequest(
  accountId: string,
  baseId: string,
  input: EditorDocumentInput,
): Promise<KbFile> {
  const { data, user } = await knowledgeRequest.put(
    accountId,
    `/${serverId(baseId)}/documents/${encodeURIComponent(input.id)}`,
    {
      title: input.title.trim().replace(/\.md$/i, "").trim() || "未命名文档",
      content: input.content,
      blocks: input.blocks ?? null,
      ...(input.preserveTitle ? { preserve_title: true } : {}),
    },
  );
  const file = toKnowledgeDocument(data as ServerKnowledgeDocument, baseId, user.username);
  if (file.id !== input.id) throw new Error("服务返回的文档 ID 无效。");
  return file;
}

/** 标题独立保存，不发送旧正文覆盖自动保存内容。 */
export async function renameKnowledgeDocumentRequest(
  accountId: string,
  baseId: string,
  id: string,
  title: string,
): Promise<KbFile> {
  const { data, user } = await knowledgeRequest.patch(
    accountId,
    `/${serverId(baseId)}/documents/${encodeURIComponent(id)}/title`,
    { title: title.trim().replace(/\.md$/i, "").trim() || "未命名文档" },
  );
  return toKnowledgeDocument(data as ServerKnowledgeDocument, baseId, user.username);
}

/** 读取知识库中的文档列表。 */
export async function listKnowledgeDocumentsRequest(
  accountId: string,
  baseId: string,
): Promise<KbFile[]> {
  const { data, user } = await knowledgeRequest.get(accountId, `/${serverId(baseId)}/documents`);
  if (!Array.isArray(data)) throw new Error("服务返回的文档列表无效。");
  return data.map((value) =>
    toKnowledgeDocument(value as ServerKnowledgeDocument, baseId, user.username),
  );
}

/** 删除知识库中的指定文档。 */
export async function deleteKnowledgeDocumentRequest(
  accountId: string,
  baseId: string,
  documentId: string,
): Promise<void> {
  await knowledgeRequest.delete(
    accountId,
    `/${serverId(baseId)}/documents/${encodeURIComponent(documentId)}`,
  );
}
