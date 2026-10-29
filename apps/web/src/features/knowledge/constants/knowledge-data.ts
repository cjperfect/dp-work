import { FileSpreadsheet, FileText, Presentation } from "lucide-react";
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

export const FILE_TYPE_META: Record<
  FileType,
  { label: string; icon: typeof FileText; badge: string }
> = {
  txt: { label: "TXT", icon: FileText, badge: "bg-slate-500/10 text-slate-600" },
  doc: { label: "Word", icon: FileText, badge: "bg-sky-500/10 text-sky-600" },
  md: { label: "Markdown", icon: FileText, badge: "bg-blue-500/10 text-blue-600" },
  pdf: { label: "PDF", icon: FileText, badge: "bg-red-500/10 text-red-600" },
  docx: { label: "Word", icon: FileText, badge: "bg-sky-500/10 text-sky-600" },
  xlsx: { label: "表格", icon: FileSpreadsheet, badge: "bg-emerald-500/10 text-emerald-600" },
  pptx: { label: "演示文稿", icon: Presentation, badge: "bg-orange-500/10 text-orange-600" },
};
