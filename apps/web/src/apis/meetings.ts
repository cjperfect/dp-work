import type { PartialBlock } from "@blocknote/core";
import { request, HttpError } from "@/lib/http";
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
  generation_ready_at?: number | null;
  generation_task_id?: string | null;
  generation_source_revision?: number | null;
};
export type Entry = {
  id: string;
  revision?: number;
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
    blocks?: PartialBlock[] | null;
    status: number;
    archived_document_id: number | string | null;
  } | null;
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

export type GenerationAccepted = {
  task_id: string;
  source_revision: number;
  meeting: Meeting;
};
/** 提交真实生成任务，由 API 固定原始内容并交给 Sidecar 执行。 */
export async function generateMinutes(workspace: Workspace): Promise<GenerationAccepted> {
  assertOwner(workspace.meeting.owner_id);
  if (workspace.meeting.status !== "ended")
    throw new MeetingError("请先结束会议，再生成会议纪要。", 409);
  return meetingRequest<GenerationAccepted>(
    workspace.meeting.owner_id,
    `/api/meetings/${encodeURIComponent(workspace.meeting.id)}/minutes/generate`,
    { method: "POST", data: { expected_revision: workspace.meeting.revision } },
  );
}
/** 构造会议工作区，用于测试和迁移旧记录。 */
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

/** 校验请求所属账号，防止切换账号后写入旧会议。 */
function assertOwner(accountId: number) {
  if (useAuthStore.getState().user?.id !== accountId)
    throw new MeetingError("登录状态已改变，请重新登录。", 401);
}
async function meetingRequest<T>(
  accountId: number,
  path: string,
  options: Parameters<typeof request>[1] = {},
) {
  assertOwner(accountId);
  const result = await request<T>(path, options);
  assertOwner(accountId);
  return result;
}
export const createMeeting = (
  accountId: number,
  body: { id: string; title: string; scheduled_at: string },
) => meetingRequest<Workspace>(accountId, "/api/meetings", { method: "POST", data: body });
export const listMeetings = (accountId: number) =>
  meetingRequest<Meeting[]>(accountId, "/api/meetings");
export async function getMeeting(accountId: number, id: string) {
  try {
    return await meetingRequest<Workspace>(accountId, `/api/meetings/${encodeURIComponent(id)}`);
  } catch (error) {
    if (error instanceof HttpError && error.status === 404) return undefined;
    throw error;
  }
}
export const saveMeeting = (accountId: number, workspace: Workspace, revision: number) =>
  meetingRequest<Workspace>(
    accountId,
    `/api/meetings/${encodeURIComponent(workspace.meeting.id)}`,
    {
      method: "PUT",
      data: {
        meeting: workspace.meeting,
        segments: workspace.segments,
        minutes: workspace.minutes,
        expected_revision: revision,
      },
    },
  );
export const importMeeting = (accountId: number, workspace: Workspace) =>
  meetingRequest<Workspace>(accountId, "/api/meetings/import", {
    method: "POST",
    data: { meeting: workspace.meeting, segments: workspace.segments, minutes: workspace.minutes },
  });
export const deleteMeeting = (accountId: number, id: string) =>
  meetingRequest<null>(accountId, `/api/meetings/${encodeURIComponent(id)}`, { method: "DELETE" });
