import { request } from "@/lib/http";
import type { FileChange, ChatThread } from "@/types/agent";

/** 从本机快照恢复一次文件修改，不上传文件正文。 */
export const undoAgentFile = (threadId: string, changeId: string) =>
  request<{ change: FileChange; thread: ChatThread }>(
    `/api/agents/threads/${threadId}/files/${changeId}/undo`,
    { method: "POST" },
  );
