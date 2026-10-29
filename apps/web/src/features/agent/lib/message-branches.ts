import {
  fromThreadMessageLike,
  type ThreadMessage,
  type ThreadAssistantMessagePart,
} from "@assistant-ui/react";
import type { ChatMessage, MessageBranch } from "@/types/agent";
import { imagePreview } from "@/apis/chat-images";

/** 将业务消息转换为 assistant-ui 的完整消息结构。 */
export function toRuntimeMessage(row: ChatMessage): ThreadMessage {
  return fromThreadMessageLike(
    {
      id: row.id,
      role: row.role,
      ...(row.role === "user"
        ? {
            attachments: (row.context.images ?? []).map((image) => ({
              id: image.id,
              type: "image" as const,
              name: image.name,
              contentType: image.content_type,
              status: { type: "complete" as const },
              content: imagePreview(image.id)
                ? [{ type: "image" as const, image: imagePreview(image.id)! }]
                : [],
            })),
          }
        : {}),
      content:
        row.role === "assistant"
          ? [...executionParts(row), { type: "text" as const, text: row.content }]
          : row.content,
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

/** 按执行事件顺序交替展示思考与工具详情。 */
function executionParts(row: ChatMessage): ThreadAssistantMessagePart[] {
  const tools = (row.context.tool_calls ?? []).map((call) => ({
    type: "tool-call" as const,
    toolCallId: call.id,
    toolName: call.name,
    args: call.args,
    argsText: JSON.stringify(call.args, null, 2),
    result:
      call.status === "running" && (row.status === "streaming" || row.status === "waiting_approval")
        ? undefined
        : call.result === undefined
          ? "执行已中断，未收到工具结果。"
          : call.result + (call.truncated ? "\n\n[结果过长，展示前 32,000 个字符]" : ""),
    isError:
      call.status === "failed" ||
      call.status === "cancelled" ||
      (call.status === "running" &&
        row.status !== "streaming" &&
        row.status !== "waiting_approval"),
    timing: {
      startedAt: call.started_at,
      ...(call.ended_at ? { completedAt: call.ended_at } : {}),
    },
  }));
  const thoughts = (row.context.reasoning ?? [])
    .filter((item) => item.text)
    .map((item) => ({
      type: "reasoning" as const,
      id: item.id,
      text: item.text,
      status: {
        type:
          item.completed_at || row.status !== "streaming"
            ? ("complete" as const)
            : ("running" as const),
      },
      timing: {
        startedAt: item.started_at,
        ...(item.completed_at ? { completedAt: item.completed_at } : {}),
      },
    }));
  const entries = [
    ...tools.map((part) => ({ key: "tool:" + part.toolCallId, part, time: part.timing.startedAt })),
    ...thoughts.map((part) => ({ key: "reasoning:" + part.id, part, time: part.timing.startedAt })),
  ];
  const ordered = row.context.execution_order ?? [];
  const fallback = entries
    .sort((a, b) => a.time - b.time)
    .map((entry) => entry.key)
    .filter((key) => !ordered.includes(key));
  const parts = new Map<string, ThreadAssistantMessagePart>(
    entries.map((entry) => [entry.key, entry.part]),
  );
  return [...fallback, ...ordered].flatMap((key) => (parts.has(key) ? [parts.get(key)!] : []));
}
