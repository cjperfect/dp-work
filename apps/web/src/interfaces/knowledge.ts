import type { PartialBlock } from "@blocknote/core";
export type FileType = "txt" | "md" | "pdf" | "doc" | "docx" | "xlsx" | "pptx";

export type KbFile = {
  id: string;
  name: string;
  type: FileType;
  size: string;
  uploader: string;
  updatedAt: string;
  /** 在线文档或可读取的文本正文 */
  content?: string;
  blocks?: PartialBlock[];
  source?: "editor" | "upload";
  storage?: "server";
  status?: "draft" | "published";
  /** 预览文件地址 */
  pdfUrl?: string;
  parseStatus?: "unparsed" | "queued" | "parsing" | "parsed" | "failed";
  parsedContent?: string;
  parseError?: string;
  parsedAt?: string;
  parsedBlocks?: PartialBlock[];
  vectorizedAt?: string;
  vectorStatus?: "unindexed" | "queued" | "indexing" | "indexed" | "failed";
  vectorError?: string;
  vectorTaskId?: string;
  vectorDone?: number;
  vectorTotal?: number;
};

export type KnowledgeBase = {
  id: string;
  name: string;
  description: string;
  owner: string;
  files: KbFile[];
  documentCount?: number;
};

export type StoredKnowledgeBase = KnowledgeBase & {
  accountId: string;
  createdAt: string;
  updatedAt: string;
  serverId?: number;
};
export type KnowledgeBaseInput = { name: string; description: string };
export type EditorDocumentInput = {
  preserveTitle?: boolean;
  id: string;
  title: string;
  content: string;
  blocks?: KbFile["blocks"];
  status: "draft" | "published";
};

/** API 原始响应结构，由映射层校验并转换为前端业务类型。 */
export type ServerKnowledgeBase = {
  id: number;
  owner_id: number;
  name: string;
  description: string;
  document_count?: number;
  created_at: string;
  updated_at: string;
};

export type ServerKnowledgeDocument = {
  id: string;
  knowledge_base_id: number;
  title: string;
  content: string;
  blocks: KbFile["blocks"] | null;
  source?: "editor" | "upload";
  file_type?: "txt" | "md" | "pdf" | "doc" | "docx";
  parse_status?: KbFile["parseStatus"];
  parse_content?: string | null;
  parse_error?: string | null;
  parsed_at?: string | null;
  parse_blocks?: KbFile["blocks"] | null;
  vectorized_at?: string | null;
  vector_status?: KbFile["vectorStatus"];
  vector_error?: string | null;
  vector_task_id?: string | null;
  vector_done?: number;
  vector_total?: number;
  original_name?: string | null;
  byte_size?: number;
  created_at: string;
  updated_at: string;
};

export type KnowledgeBasePage = {
  item: StoredKnowledgeBase[];
  total: number;
  page: number;
  page_size: number;
};
