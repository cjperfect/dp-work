import type { KbFile } from "@/interfaces/knowledge";
import {
  listLocalEditorDocuments,
  removeLocalEditorDocuments,
} from "@/features/knowledge/lib/legacy-documents";
import { listKnowledgeDocumentsRequest, saveKnowledgeDocumentRequest } from "./documents";

/** 旧版浏览器文档仅迁移一次，服务端已有同 ID 时保留数据库版本。 */
const documentLoads = new Map<string, Promise<KbFile[]>>();

/** 加载文档并合并同一知识库的并发请求。 */
export async function loadKnowledgeDocumentsRequest(
  accountId: string,
  baseId: string,
): Promise<KbFile[]> {
  const key = `${accountId}:${baseId}`;
  const existing = documentLoads.get(key);
  if (existing) return existing;
  const promise = migrateKnowledgeDocuments(accountId, baseId);
  documentLoads.set(key, promise);
  try {
    return await promise;
  } finally {
    if (documentLoads.get(key) === promise) documentLoads.delete(key);
  }
}

/** 将旧版本地文档迁移到服务端。 */
async function migrateKnowledgeDocuments(accountId: string, baseId: string): Promise<KbFile[]> {
  const files = await listKnowledgeDocumentsRequest(accountId, baseId);
  const local = listLocalEditorDocuments(accountId, baseId);
  const existing = new Set(files.map((file) => file.id));
  for (const file of local) {
    if (!existing.has(file.id)) {
      files.push(
        await saveKnowledgeDocumentRequest(accountId, baseId, {
          id: file.id,
          title: file.name,
          content: file.content ?? "",
          blocks: file.blocks,
          status: "published",
        }),
      );
    }
    removeLocalEditorDocuments(accountId, baseId, [file.id]);
  }
  return files;
}
