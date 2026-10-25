import type { PartialBlock } from "@blocknote/core";
import { readMock, writeMock } from "@/lib/mock-storage";
import { canEditMinutes } from "./minutes-state";
import type { Workspace } from "@/apis/meetings";
import { readDraft, saveDraft } from "./workspace-storage";
import { publish } from "@/stores/meetings";
export type LocalShare = {
  token: string;
  owner: number;
  meetingId: string;
  permission: "read" | "edit";
};
export function createLocalShare(workspace: Workspace, permission: "read" | "edit") {
  const key = `share-link:${workspace.meeting.owner_id}:${workspace.meeting.id}:${permission}`;
  const existing = readMock<string>(key);
  if (existing) {
    const share = readMock<LocalShare>(`share:${existing}`);
    if (
      share?.meetingId === workspace.meeting.id &&
      share.owner === workspace.meeting.owner_id &&
      share.permission === permission
    )
      return new URL(`/shared/meetings/${existing}`, window.location.origin).href;
  }
  const token = crypto.randomUUID();
  writeMock<LocalShare>(`share:${token}`, {
    token,
    owner: workspace.meeting.owner_id,
    meetingId: workspace.meeting.id,
    permission,
  });
  writeMock(key, token);
  return new URL(`/shared/meetings/${token}`, window.location.origin).href;
}
export async function readLocalShare(token: string) {
  const share = readMock<LocalShare>(`share:${token}`);
  if (!share) throw new Error("分享链接不存在，或不在创建链接的浏览器中。");
  const draft = await readDraft(share.owner, share.meetingId);
  if (!draft) throw new Error("会议已被删除，分享链接已失效。");
  return { share, draft };
}
export async function saveSharedMinutes(token: string, content: string, blocks?: PartialBlock[]) {
  const { share, draft } = await readLocalShare(token);
  if (share.permission !== "edit") throw new Error("此链接仅可阅读。");
  if (!canEditMinutes(draft.meeting)) throw new Error("当前会议仅可阅读。");
  const stored = await saveDraft({
    ...draft,
    minutes: {
      content,
      blocks,
      status: 1,
      archived_document_id: draft.minutes?.archived_document_id ?? null,
    },
    version: draft.version + 1,
  });
  publish(stored);
  return stored;
}
