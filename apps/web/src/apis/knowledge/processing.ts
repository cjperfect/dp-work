import type { KbFile, ServerKnowledgeDocument } from "@/interfaces/knowledge";
import { knowledgeRequest, serverId } from "./client";
import { toKnowledgeDocument } from "./mappers";

/** 提交文档解析任务。 */
export async function parseKnowledgeDocumentRequest(
  accountId: string,
  baseId: string,
  documentId: string,
): Promise<KbFile> {
  const { data, user } = await knowledgeRequest.post(
    accountId,
    `/${serverId(baseId)}/documents/${encodeURIComponent(documentId)}/parse`,
  );
  return toKnowledgeDocument(data as ServerKnowledgeDocument, baseId, user.username);
}

/** 保存人工编辑后的解析内容。 */
export async function saveParsedDocumentRequest(
  accountId: string,
  baseId: string,
  documentId: string,
  input: { content: string; blocks: KbFile["blocks"]; expected_parsed_at: string },
): Promise<KbFile> {
  const { data, user } = await knowledgeRequest.put(
    accountId,
    `/${serverId(baseId)}/documents/${encodeURIComponent(documentId)}/parsed`,
    input,
  );
  return toKnowledgeDocument(data as ServerKnowledgeDocument, baseId, user.username);
}

/** 基于已保存的解析版本提交父子分块向量化。 */
export async function vectorizeKnowledgeDocumentRequest(
  accountId: string,
  baseId: string,
  file: KbFile,
): Promise<KbFile> {
  if (!file.parsedAt) throw new Error("请先解析并保存文档。");
  const { data, user } = await knowledgeRequest.post(
    accountId,
    `/${serverId(baseId)}/documents/${encodeURIComponent(file.id)}/vectorize`,
    { expected_parsed_at: file.parsedAt },
  );
  return toKnowledgeDocument(data as ServerKnowledgeDocument, baseId, user.username);
}
