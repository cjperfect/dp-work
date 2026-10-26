import type { Workspace } from "@/apis/meetings";

/** 已有纪要优先；尚无纪要时展示确认后的会议转写。 */
export function minutesContent(workspace: Workspace): string {
  if (workspace.minutes) return workspace.minutes.content;
  return originalMeetingContent(workspace);
}

/** 导出原始转写，不使用编辑过的纪要草稿。 */
export function originalMeetingContent(workspace: Workspace): string {
  return workspace.segments
    .map((row) => `${row.speaker ? `${row.speaker}：` : ""}${row.text}`)
    .join("\n\n");
}
