import type {
  KbFile,
  StoredKnowledgeBase,
  ServerKnowledgeBase,
  ServerKnowledgeDocument,
} from "@/interfaces/knowledge";
import { serverId } from "./client";

/** 校验知识库响应并转换为前端模型。 */
export function toStoredKnowledgeBase(
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

/** 校验文档响应并转换为前端模型。 */
export function toKnowledgeDocument(
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
    parseStatus: value.parse_status ?? "unparsed",
    parsedContent: value.parse_content ?? undefined,
    parseError: value.parse_error ?? undefined,
    parsedAt: value.parsed_at ?? undefined,
    parsedBlocks: value.parse_blocks ?? undefined,
    vectorizedAt: value.vectorized_at ?? undefined,
    vectorStatus: value.vector_status ?? "unindexed",
    vectorError: value.vector_error ?? undefined,
    vectorTaskId: value.vector_task_id ?? undefined,
    vectorDone: value.vector_done ?? 0,
    vectorTotal: value.vector_total ?? 0,
    storage: "server",
    status: "published",
    content: value.content,
    blocks: value.blocks ?? undefined,
    size: formatDocumentSize(value.byte_size || new TextEncoder().encode(value.content).byteLength),
    uploader: username,
    updatedAt: value.updated_at,
  };
}

/** 将文件字节数格式化为 KB 或 MB。 */
function formatDocumentSize(bytes: number) {
  return bytes >= 1024 * 1024
    ? `${(bytes / (1024 * 1024)).toFixed(1)} MB`
    : `${Math.max(1, Math.ceil(bytes / 1024))} KB`;
}
