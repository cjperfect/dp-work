import type { ChatThread, ThreadDetail } from "@/interfaces/agent";
import { http } from "@/lib/http";

import { hydrateChatImages } from "./chat-images";

const root = "/api/agents/threads";
/** 获取当前账号的全部会话。 */
export const listConversations = () => http.get<ChatThread[]>(root);
/** 读取会话详情并恢复图片预览。 */
export const getConversation = async (id: string) =>
  hydrateChatImages(await http.get<ThreadDetail>(`${root}/${id}`));
/** 创建指定 Agent 的草稿会话。 */
export const createConversation = (
  id: string,
  agent_id: number,
  knowledge_base_ids: (string | number)[],
  project_id: string | null = null,
) => http.post<ThreadDetail>(root, { id, agent_id, knowledge_base_ids, project_id });
/** 保存会话消息及分支。 */
export const saveConversationMessages = (id: string, detail: ThreadDetail) =>
  http.put<ThreadDetail>(`${root}/${id}/messages`, {
    expected_revision: detail.thread.draft_revision,
    messages: detail.messages,
    message_branches: detail.message_branches ?? [],
  });
/** 保存手动修改或模型生成的会话标题。 */
export const renameConversation = (
  id: string,
  title: string,
  title_source: "manual" | "generated" = "manual",
  first_message_id?: string,
) => http.patch<ChatThread>(`${root}/${id}`, { title, title_source, first_message_id });
/** 删除指定会话。 */
export const deleteConversation = (id: string) => http.delete<null>(`${root}/${id}`);
/** 迁移本机会话历史。 */
export const importConversation = (detail: ThreadDetail) =>
  http.post<ThreadDetail | null>(`${root}/import`, {
    ...detail,
    expected_revision: 0,
    message_branches: detail.message_branches ?? [],
  });
