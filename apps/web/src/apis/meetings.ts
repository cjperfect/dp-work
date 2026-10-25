import type { PartialBlock } from "@blocknote/core";
import { useAuthStore } from "@/stores/auth";

export type Meeting = {
  id: string;
  owner_id: number;
  title: string;
  scheduled_at: string;
  participants: string[];
  status: "active" | "paused" | "ended" | "archived";
  elapsed_ms: number;
  resumed_at: string | null;
  ended_at: string | null;
  revision: number;
  created_at: string;
  updated_at: string;
  minutes_status?: number | null;
  generation_status?: "idle" | "generating" | "ready" | "failed";
  generation_error?: string | null;
  generation_ready_at?: number;
};
export type Entry = {
  id: string;
  seq: number;
  speaker: string | null;
  text: string;
  start_ms: number;
  end_ms?: number | null;
};
export type Workspace = {
  meeting: Meeting;
  segments: Entry[];
  minutes: {
    content: string;
    blocks?: PartialBlock[];
    status: number;
    archived_document_id: number | null;
  } | null;
};
export type SyncPayload = {
  expected_revision: number;
  sync_id: string;
  controls?: Pick<Meeting, "status" | "elapsed_ms" | "resumed_at">;
  segments: Entry[];
  minutes?: string;
};
export class MeetingError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message);
  }
}

/** 模拟分享接口：链接在同一浏览器中可阅读或编辑。 */
export async function createMinutesShare(
  workspace: Workspace,
  permission: "read" | "edit",
): Promise<string> {
  if (useAuthStore.getState().user?.id !== workspace.meeting.owner_id)
    throw new MeetingError("登录状态已改变，请重新登录。", 401);
  const { createLocalShare } = await import("@/features/meetings/lib/mock-sharing");
  return createLocalShare(workspace, permission);
}
export const DEMO_MINUTES = `## 会议结论
- 优先完成会议记录、纪要编辑与知识库归档的完整流程。
- 会议重点通过导图展示，方便快速回顾。

## 行动项
- 产品团队：整理本轮需求与验收标准。
- 研发团队：完成交互联调并验证分享权限。

## 后续安排
- 下次会议回顾交付进度，确认待讨论事项。

> 当前内容为本地模拟生成，用于体验页面流程。`;

/** 生成接口未接入：仅保留已有纪要，配合本地状态完成提交和跳转。 */
export async function generateMinutes(workspace: Workspace): Promise<{ content: string }> {
  if (useAuthStore.getState().user?.id !== workspace.meeting.owner_id)
    throw new MeetingError("登录状态已改变，请重新登录。", 401);
  if (workspace.meeting.status !== "ended")
    throw new MeetingError("请先结束会议，再生成会议纪要。", 409);
  return { content: workspace.minutes?.content ?? "" };
}
export function applyGeneratedMinutes<T extends Workspace>(
  workspace: T,
  result: { content: string },
): T {
  return {
    ...workspace,
    meeting: {
      ...workspace.meeting,
      minutes_status: 0,
      generation_status: "generating",
      generation_error: null,
      generation_ready_at: undefined,
    },
    minutes: {
      blocks: workspace.minutes?.blocks,
      content: result.content,
      status: 0,
      archived_document_id: workspace.minutes?.archived_document_id ?? null,
    },
  };
}
/** 业务 API 已下线：本地构造一个空会议工作区，供静态占位使用。 */
export function emptyWorkspace(id: string, ownerId: number, title = "未命名会议"): Workspace {
  const now = new Date().toISOString();
  return {
    meeting: {
      id,
      owner_id: ownerId,
      title,
      scheduled_at: now,
      participants: [],
      status: "active",
      elapsed_ms: 0,
      resumed_at: null,
      ended_at: null,
      revision: 1,
      created_at: now,
      updated_at: now,
    },
    segments: [],
    minutes: null,
  };
}
export const STATUS_LABELS = {
  active: "进行中",
  paused: "已暂停",
  ended: "已结束",
  archived: "已归档",
};
export function elapsed(
  meeting: Pick<Meeting, "elapsed_ms" | "resumed_at" | "status">,
  now = Date.now(),
) {
  return (
    meeting.elapsed_ms +
    (meeting.status === "active" && meeting.resumed_at
      ? Math.max(0, now - Date.parse(meeting.resumed_at))
      : 0)
  );
}
export function duration(ms: number) {
  const seconds = Math.floor(ms / 1000);
  return `${String(Math.floor(seconds / 3600)).padStart(2, "0")}:${String(Math.floor(seconds / 60) % 60).padStart(2, "0")}:${String(seconds % 60).padStart(2, "0")}`;
}
export function exportMarkdown(title: string, content: string) {
  const url = URL.createObjectURL(
    new Blob([`# ${title}\n\n${content}`], { type: "text/markdown;charset=utf-8" }),
  );
  const link = document.createElement("a");
  link.href = url;
  link.download = `${title.replace(/[\\/:*?"<>|]/g, "_") || "会议纪要"}.md`;
  link.click();
  URL.revokeObjectURL(url);
}
