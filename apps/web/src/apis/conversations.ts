import { request } from "@/lib/http";
import type { ChatThread, MessageBranch, ThreadDetail } from "@/types/agent";

const root = "/api/agents/threads";
export const listConversations = () => request<ChatThread[]>(root);
export const getConversation = (id: string) => request<ThreadDetail>(`${root}/${id}`);
export const createConversation = (
  id: string,
  agent_id: number,
  knowledge_base_ids: (string | number)[],
) => request<ThreadDetail>(root, { method: "POST", data: { id, agent_id, knowledge_base_ids } });
export const saveConversationDraft = (
  id: string,
  data: { expected_revision: number; draft: string; knowledge_base_ids: (string | number)[] },
) => request<ChatThread>(`${root}/${id}/draft`, { method: "PATCH", data });
export const saveConversationMessages = (id: string, detail: ThreadDetail) =>
  request<ThreadDetail>(`${root}/${id}/messages`, {
    method: "PUT",
    data: {
      expected_revision: detail.thread.draft_revision,
      messages: detail.messages,
      message_branches: detail.message_branches ?? [],
    },
  });
export const renameConversation = (
  id: string,
  title: string,
  title_source: "manual" | "generated" = "manual",
  first_message_id?: string,
) =>
  request<ChatThread>(`${root}/${id}`, {
    method: "PATCH",
    data: { title, title_source, first_message_id },
  });
export const deleteConversation = (id: string) =>
  request<null>(`${root}/${id}`, { method: "DELETE" });
export const importConversation = (detail: ThreadDetail) =>
  request<ThreadDetail | null>(`${root}/import`, {
    method: "POST",
    data: { ...detail, expected_revision: 0, message_branches: detail.message_branches ?? [] },
  });
export type { MessageBranch };
