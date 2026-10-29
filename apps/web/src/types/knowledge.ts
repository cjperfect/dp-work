import type { KnowledgeBase, KbFile } from "@/features/knowledge/constants/knowledge-data";

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
