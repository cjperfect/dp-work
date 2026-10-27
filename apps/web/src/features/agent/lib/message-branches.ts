import { fromThreadMessageLike, type ThreadMessage } from "@assistant-ui/react";
import type { ChatMessage, MessageBranch } from "@/types/agent";

/** 将业务消息转换为 assistant-ui 的完整消息结构。 */
export function toRuntimeMessage(row: ChatMessage): ThreadMessage {
  return fromThreadMessageLike(
    {
      id: row.id,
      role: row.role,
      content: row.content,
      createdAt: new Date(row.created_at),
      metadata: { custom: { ...row.context, local_status: row.status } },
    },
    row.id,
    row.status === "streaming"
      ? { type: "running" }
      : row.status === "failed"
        ? { type: "incomplete", reason: "error" }
        : row.status === "cancelled"
          ? { type: "incomplete", reason: "cancelled" }
          : { type: "complete", reason: "stop" },
  );
}

/** 从运行时导出已有分支，也兼容当前页面尚未持久化的旧版本。 */
export function readRuntimeBranches(
  entries: readonly { message: ThreadMessage; parentId: string | null }[],
  known: readonly MessageBranch[],
): MessageBranch[] {
  const existing = new Map(known.map((entry) => [entry.message.id, entry.message]));
  const fallback = known[0]?.message.context;
  return entries.flatMap(({ message, parentId }) => {
    if (message.role !== "user" && message.role !== "assistant") return [];
    const previous = existing.get(message.id);
    if (previous) return [{ parentId, message: previous }];
    const custom = message.metadata.custom;
    const context =
      typeof custom.agent === "object" && custom.agent !== null
        ? ({
            agent: custom.agent,
            skills: custom.skills ?? [],
            knowledge_bases: custom.knowledge_bases ?? [],
          } as ChatMessage["context"])
        : fallback;
    if (!context) return [];
    return [
      {
        parentId,
        message: {
          id: message.id,
          seq: 0,
          role: message.role,
          content: message.content
            .filter((part) => part.type === "text")
            .map((part) => part.text)
            .join("\n"),
          created_at: message.createdAt.toISOString(),
          context,
          status: (custom.local_status as ChatMessage["status"]) ?? "complete",
        },
      },
    ];
  });
}
