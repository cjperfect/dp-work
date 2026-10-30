import type { KbFile, ServerKnowledgeDocument } from "@/interfaces/knowledge";
import { knowledgeRequest, serverId } from "./client";
import { toKnowledgeDocument } from "./mappers";

export const MAX_UPLOAD_SIZE = 20 * 1024 * 1024;

/** 上传源文件并返回文档信息。 */
export async function uploadKnowledgeDocumentRequest(
  accountId: string,
  baseId: string,
  file: File,
  onProgress?: (percent: number) => void,
): Promise<KbFile> {
  if (!/\.(txt|md|markdown|pdf|doc|docx)$/i.test(file.name))
    throw new Error("仅支持 TXT、Markdown、PDF 和 Word 文件。");
  if (file.size > MAX_UPLOAD_SIZE) throw new Error("单个文件不能超过 20 MB。");
  const form = new FormData();
  form.append("file", file);
  const { data, user } = await knowledgeRequest.post(
    accountId,
    `/${serverId(baseId)}/documents/upload`,
    form,
    {
      timeout: 120000,
      /** 更新文件上传进度。 */
      onUploadProgress: (event) => {
        if (event.total) onProgress?.(Math.round((event.loaded * 100) / event.total));
      },
    },
  );
  return toKnowledgeDocument(data as ServerKnowledgeDocument, baseId, user.username);
}

/** 下载文档源文件。 */
export async function downloadKnowledgeDocumentRequest(
  accountId: string,
  baseId: string,
  documentId: string,
  signal?: AbortSignal,
): Promise<Blob> {
  const { data } = await knowledgeRequest.get(
    accountId,
    `/${serverId(baseId)}/documents/${encodeURIComponent(documentId)}/file`,
    { responseType: "blob", signal },
  );
  if (!(data instanceof Blob)) throw new Error("源文件数据无效。");
  return data;
}
