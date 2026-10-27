import type { AgentId } from "@/interfaces/app";
export type AgentConfig = {
  id: number;
  owner_id: number;
  code: AgentId;
  name: string;
  department: string;
  description: string;
  knowledge_base_ids: (string | number)[];
  skill_ids: string[];
  revision: number;
  active_thread_id: string | null;
};
export type Skill = { id: string; name: string; department: string; description: string };
export type ChatThread = {
  title_source?: "pending" | "generated" | "manual";
  id: string;
  agent_id: number;
  title: string;
  draft: string;
  draft_revision: number;
  created_at: string;
  updated_at: string;
};
export type ChatMessage = {
  status?: "streaming" | "complete" | "failed" | "cancelled";
  id: string;
  seq: number;
  role: "user" | "assistant";
  content: string;
  created_at: string;
  context: {
    knowledge_bases: { id: number; name: string }[];
    skills: Skill[];
    agent: { id: number; name: string; department: string; revision: number };
  };
};
export type MessageBranch = { parentId: string | null; message: ChatMessage };

export type ThreadDetail = {
  message_branches?: MessageBranch[];
  thread: ChatThread;
  knowledge_base_ids: (string | number)[];
  messages: ChatMessage[];
};
