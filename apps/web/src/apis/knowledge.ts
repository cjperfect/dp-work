import { HttpError, request, type RequestOptions } from "@/lib/http";
import { getAccessToken, useAuthStore } from "@/stores/auth";
import type { KbFile } from "@/features/knowledge/constants/knowledge-data";
import {
  listLocalEditorDocuments,
  removeLocalEditorDocuments,
} from "@/features/knowledge/lib/knowledge-repository";
import type {
  EditorDocumentInput,
  KnowledgeBaseInput,
  StoredKnowledgeBase,
} from "@/features/knowledge/lib/knowledge-repository";

type ServerKnowledgeBase = {
  id: number;
  owner_id: number;
  name: string;
  description: string;
  document_count?: number;
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
    documentCount: data.document_count ?? 0,
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

type ServerKnowledgeDocument = {
  id: string;
  knowledge_base_id: number;
  title: string;
  content: string;
  blocks: KbFile["blocks"] | null;
  source?: "editor" | "upload";
  file_type?: "md" | "pdf";
  original_name?: string | null;
  byte_size?: number;
  created_at: string;
  updated_at: string;
};

function toKnowledgeDocument(
  value: ServerKnowledgeDocument,
  baseId: string,
  username: string,
): KbFile {
  if (
    !value ||
    typeof value.id !== "string" ||
    value.knowledge_base_id !== serverId(baseId) ||
    [value.title, value.content, value.created_at, value.updated_at].some(
      (item) => typeof item !== "string",
    ) ||
    (value.blocks !== null && !Array.isArray(value.blocks))
  )
    throw new Error("服务返回的文档数据无效。");
  return {
    id: value.id,
    name: value.original_name ?? `${value.title}.md`,
    type: value.file_type ?? "md",
    source: value.source ?? "editor",
    storage: "server",
    status: "published",
    content: value.content,
    blocks: value.blocks ?? undefined,
    size: formatDocumentSize(value.byte_size || new TextEncoder().encode(value.content).byteLength),
    uploader: username,
    updatedAt: value.updated_at,
  };
}

export async function saveKnowledgeDocumentRequest(
  accountId: string,
  baseId: string,
  input: EditorDocumentInput,
): Promise<KbFile> {
  const { data, user } = await knowledgeRequest(
    accountId,
    `/${serverId(baseId)}/documents/${encodeURIComponent(input.id)}`,
    {
      method: "PUT",
      data: {
        title: input.title.trim().replace(/\.md$/i, "").trim() || "未命名文档",
        content: input.content,
        blocks: input.blocks ?? null,
      },
    },
  );
  const file = toKnowledgeDocument(data as ServerKnowledgeDocument, baseId, user.username);
  if (file.id !== input.id) throw new Error("服务返回的文档 ID 无效。");
  return file;
}

export async function listKnowledgeDocumentsRequest(
  accountId: string,
  baseId: string,
): Promise<KbFile[]> {
  const { data, user } = await knowledgeRequest(accountId, `/${serverId(baseId)}/documents`, {
    method: "GET",
  });
  if (!Array.isArray(data)) throw new Error("服务返回的文档列表无效。");
  return data.map((value) =>
    toKnowledgeDocument(value as ServerKnowledgeDocument, baseId, user.username),
  );
}

/** 旧版浏览器文档仅迁移一次，SQLite 中已有同 ID 时保留数据库版本。 */
const documentLoads = new Map<string, Promise<KbFile[]>>();

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

export async function deleteKnowledgeDocumentRequest(
  accountId: string,
  baseId: string,
  documentId: string,
): Promise<void> {
  await knowledgeRequest(
    accountId,
    `/${serverId(baseId)}/documents/${encodeURIComponent(documentId)}`,
    { method: "DELETE" },
  );
}

export const MAX_UPLOAD_SIZE = 20 * 1024 * 1024;

function formatDocumentSize(bytes: number) {
  return bytes >= 1024 * 1024
    ? `${(bytes / (1024 * 1024)).toFixed(1)} MB`
    : `${Math.max(1, Math.ceil(bytes / 1024))} KB`;
}

export async function uploadKnowledgeDocumentRequest(
  accountId: string,
  baseId: string,
  file: File,
  onProgress?: (percent: number) => void,
): Promise<KbFile> {
  if (!/\.(md|pdf)$/i.test(file.name)) throw new Error("仅支持 Markdown 与 PDF 文件。");
  if (file.size > MAX_UPLOAD_SIZE) throw new Error("单个文件不能超过 20 MB。");
  const form = new FormData();
  form.append("file", file);
  const { data, user } = await knowledgeRequest(
    accountId,
    `/${serverId(baseId)}/documents/upload`,
    {
      method: "POST",
      data: form,
      timeout: 120000,
      onUploadProgress: (event) => {
        if (event.total) onProgress?.(Math.round((event.loaded * 100) / event.total));
      },
    },
  );
  return toKnowledgeDocument(data as ServerKnowledgeDocument, baseId, user.username);
}

export async function downloadKnowledgeDocumentRequest(
  accountId: string,
  baseId: string,
  documentId: string,
): Promise<Blob> {
  const { data } = await knowledgeRequest(
    accountId,
    `/${serverId(baseId)}/documents/${encodeURIComponent(documentId)}/file`,
    { responseType: "blob" },
  );
  if (!(data instanceof Blob)) throw new Error("源文件数据无效。");
  return data;
}
