import type { LocalProject } from "@dp-work/protocols/desktop";
import type { AgentId } from "@/interfaces/app";
import type { ToolCallMessagePart } from "@assistant-ui/react";
export type ChatImage = { id: string; name: string; content_type: string };
export type UsageCall = {
  id: string;
  model: string;
  status: "running" | "reported" | "unreported";
  input_tokens?: number;
  output_tokens?: number;
  total_tokens?: number;
  cached_input_tokens?: number;
  reasoning_tokens?: number;
  estimated_cost?: string;
  currency: string;
};
export type RunUsage = {
  run_id: string;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  cached_input_tokens: number;
  reasoning_tokens: number;
  cached_input_reported?: boolean;
  reasoning_reported?: boolean;
  calls: UsageCall[];
  reported_calls: number;
  unreported_calls: number;
  in_flight_calls: number;
  complete: boolean;
  estimated_cost: string | null;
  currency: string;
  token_limit: number | null;
  cost_limit: string | null;
};
export type ReasoningSegment = {
  id: string;
  text: string;
  started_at: number;
  completed_at?: number;
};
export type FileChange = {
  id: string;
  path: string;
  additions: number;
  deletions: number;
  lines: { kind: "context" | "added" | "removed"; text: string }[];
  truncated?: boolean;
  unavailable?: string;
  kind?: "created" | "modified" | "deleted";
  undoable?: boolean;
  undone?: boolean;
  undo_unavailable?: string;
};
export type ToolExecution = {
  id: string;
  name: string;
  args: ToolCallMessagePart["args"];
  status: "running" | "complete" | "failed" | "cancelled";
  started_at: number;
  ended_at?: number;
  result?: string;
  truncated?: boolean;
};
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
  has_history?: boolean;
  project_id?: string | null;
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
  status?: "streaming" | "waiting_approval" | "complete" | "failed" | "cancelled";
  id: string;
  seq: number;
  role: "user" | "assistant";
  content: string;
  created_at: string;
  context: {
    memory_sources?: import("@/interfaces/memory").MemorySource[];
    execution_run_id?: string;
    usage?: RunUsage;
    reasoning?: ReasoningSegment[];
    execution_order?: string[];
    images?: ChatImage[];
    file_changes?: FileChange[];
    tool_calls?: ToolExecution[];
    steering_run_id?: string;
    steering_status?: "queued" | "applied";
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

export type ReasoningEvent = {
  id: string;
  text?: string;
  started_at: number;
  completed_at?: number;
};

export type SteeringEvent = {
  id: string;
  response_id: string;
  previous_response_id: string;
  previous_content: string;
  previous_removed: boolean;
  thread: ChatThread;
  message: ChatMessage;
  response: ChatMessage;
};

export type AgentModels = { configured: boolean; models: { id: string; name: string }[] };

export type AgentChatInput = {
  approval_request?: { id: string; decision: "approve" | "reject" };
  response_id?: string;
  expected_revision?: number;
  agent_code: AgentId;
  thread_id: string;
  messages: { role: "user" | "assistant"; content: string }[];
  model?: string;
  knowledge_base_ids?: number[];
};

export type AgentRuntimeConfig = { agent_code: AgentId; prompt: string; prompt_file: string };

export type AgentApproval = {
  id: string;
  run_id: string;
  conversation_id: string;
  response_id: string;
  status: "pending" | "approved" | "rejected";
  actionable: boolean;
  interrupts: {
    id: string;
    value: {
      action_requests: { name: string; args: Record<string, unknown>; description?: string }[];
    };
  }[];
  created_at: string;
  decided_at: string | null;
};

export type AgentProject = LocalProject & { created_at: string; updated_at: string };

export type AgentMeta = {
  id: AgentId;
  numericId: number;
  capabilities: string[];
  name: string;
  department: string;
  description: string;
  skills: string[];
};
