import type { Meeting, Workspace, GenerationAccepted } from "@/interfaces/meeting";
import { http, HttpError } from "@/lib/http";
import { useAuthStore } from "@/stores/auth";

export class MeetingError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message);
  }
}

/** 提交真实生成任务，由 API 固定原始内容并交给 Sidecar 执行。 */
export async function generateMinutes(workspace: Workspace): Promise<GenerationAccepted> {
  assertOwner(workspace.meeting.owner_id);
  if (workspace.meeting.status !== "ended")
    throw new MeetingError("请先结束会议，再生成会议纪要。", 409);
  return meetingRequest.post<GenerationAccepted>(
    workspace.meeting.owner_id,
    `/api/meetings/${encodeURIComponent(workspace.meeting.id)}/minutes/generate`,
    { expected_revision: workspace.meeting.revision },
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
/** 计算会议当前累计时长。 */
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
/** 将会议时长格式化为时分秒。 */
export function duration(ms: number) {
  const seconds = Math.floor(ms / 1000);
  return `${String(Math.floor(seconds / 3600)).padStart(2, "0")}:${String(Math.floor(seconds / 60) % 60).padStart(2, "0")}:${String(seconds % 60).padStart(2, "0")}`;
}
/** 将会议内容下载为 Markdown 文件。 */
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
/** 执行会议请求并防止跨账号写回。 */
async function guardedMeetingRequest<T>(accountId: number, execute: () => Promise<T>) {
  assertOwner(accountId);
  const result = await execute();
  assertOwner(accountId);
  return result;
}
const meetingRequest = {
  /** 发送查询请求并校验当前账号。 */
  get: <T>(account: number, path: string) =>
    guardedMeetingRequest(account, () => http.get<T>(path)),
  /** 发送新增或执行请求并校验当前账号。 */
  post: <T>(account: number, path: string, data?: unknown) =>
    guardedMeetingRequest(account, () => http.post<T>(path, data)),
  /** 发送更新请求并校验当前账号。 */
  put: <T>(account: number, path: string, data?: unknown) =>
    guardedMeetingRequest(account, () => http.put<T>(path, data)),
  /** 发送删除请求并校验当前账号。 */
  delete: <T>(account: number, path: string) =>
    guardedMeetingRequest(account, () => http.delete<T>(path)),
};
/** 创建会议及其基础信息。 */
export const createMeeting = (
  accountId: number,
  body: { id: string; title: string; scheduled_at: string },
) => meetingRequest.post<Workspace>(accountId, "/api/meetings", body);
/** 读取当前账号的会议列表。 */
export const listMeetings = (accountId: number) =>
  meetingRequest.get<Meeting[]>(accountId, "/api/meetings");
/** 读取会议工作区，不存在时返回空值。 */
export async function getMeeting(accountId: number, id: string) {
  try {
    return await meetingRequest.get<Workspace>(
      accountId,
      `/api/meetings/${encodeURIComponent(id)}`,
    );
  } catch (error) {
    if (error instanceof HttpError && error.status === 404) return undefined;
    throw error;
  }
}
/** 按版本保存会议状态、转写和纪要。 */
export const saveMeeting = (accountId: number, workspace: Workspace, revision: number) =>
  meetingRequest.put<Workspace>(
    accountId,
    `/api/meetings/${encodeURIComponent(workspace.meeting.id)}`,
    {
      meeting: workspace.meeting,
      segments: workspace.segments,
      minutes: workspace.minutes,
      expected_revision: revision,
    },
  );
/** 迁移已有会议工作区。 */
export const importMeeting = (accountId: number, workspace: Workspace) =>
  meetingRequest.post<Workspace>(accountId, "/api/meetings/import", {
    meeting: workspace.meeting,
    segments: workspace.segments,
    minutes: workspace.minutes,
  });
/** 删除指定会议。 */
export const deleteMeeting = (accountId: number, id: string) =>
  meetingRequest.delete<null>(accountId, `/api/meetings/${encodeURIComponent(id)}`);
