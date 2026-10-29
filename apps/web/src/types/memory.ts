export type MemoryScope = "user" | "agent" | "project";
export type MemoryKind = "preference" | "fact" | "experience";
export type MemoryWrite = {
  title: string;
  content: string;
  kind: MemoryKind;
  scope: MemoryScope;
  agent_code: "general" | "product" | "ui" | null;
  project_id: string | null;
  enabled: boolean;
  expires_at?: string | null;
};
export type Memory = MemoryWrite & {
  id: string;
  revision: number;
  source: "manual" | "automatic";
  created_at: string;
  updated_at: string;
  expires_at: string | null;
};
export type MemorySource = Pick<Memory, "id" | "title" | "kind" | "scope" | "revision">;
export type MemoryQuery = {
  q?: string;
  scope?: MemoryScope;
  kind?: MemoryKind;
  page: number;
  page_size: number;
};
export type MemoryPage = { item: Memory[]; page: number; page_size: number; total: number };
export type MemoryPreference = { enabled: boolean; auto_generate: boolean; revision: number };
export const MEMORY_SCOPES = { user: "用户", agent: "Agent", project: "项目" } as const;
export const MEMORY_KINDS = {
  preference: "偏好与约定",
  fact: "项目事实",
  experience: "已验证经验",
} as const;
