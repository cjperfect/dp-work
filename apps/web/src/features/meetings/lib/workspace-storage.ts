import { deleteMeeting, getMeeting, listMeetings, saveMeeting } from "@/apis/meetings";
import { migrateLegacyMeetings } from "./legacy-meetings";
import type { Meeting, Workspace } from "@/apis/meetings";
export type Draft = Workspace & {
  accountId: number;
  version: number;
  dirtyControls: boolean;
  dirtyMinutes: boolean;
  dirtyEntries: string[];
  temporary: { id?: string; seq?: number; revision?: number; speaker: string; text: string };
  error: string | null;
};
export const isPending = (draft: Draft) =>
  draft.dirtyControls || draft.dirtyMinutes || draft.dirtyEntries.length > 0;
export function localDraft(workspace: Workspace): Draft {
  return {
    ...workspace,
    accountId: workspace.meeting.owner_id,
    version: 0,
    dirtyControls: false,
    dirtyMinutes: false,
    dirtyEntries: [],
    temporary: { speaker: "", text: "" },
    error: null,
  };
}

const heads = new Map<string, { revision: number; version: number }>();
const queues = new Map<string, Promise<unknown>>();
const key = (owner: number, id: string) => `${owner}:${id}`;

export async function readDraft(accountId: number, id: string): Promise<Draft | undefined> {
  await migrateLegacyMeetings(accountId);
  const workspace = await getMeeting(accountId, id);
  if (!workspace) return undefined;
  const cacheKey = key(accountId, id);
  const head = heads.get(cacheKey);
  if (!queues.has(cacheKey))
    heads.set(cacheKey, { revision: workspace.meeting.revision, version: head?.version ?? 0 });
  return { ...localDraft(workspace), version: head?.version ?? 0 };
}
const listRequests = new Map<number, Promise<Meeting[]>>();
/** 合并同一账号进行中的列表请求，完成后下次进入仍重新查询。 */
export function listSavedMeetings(accountId: number): Promise<Meeting[]> {
  const existing = listRequests.get(accountId);
  if (existing) return existing;
  const operation = (async () => {
    await migrateLegacyMeetings(accountId);
    return listMeetings(accountId);
  })();
  listRequests.set(accountId, operation);
  void operation
    .finally(() => {
      if (listRequests.get(accountId) === operation) listRequests.delete(accountId);
    })
    .catch(() => {});
  return operation;
}
export async function listDrafts(accountId: number) {
  const meetings = await listSavedMeetings(accountId);
  return (await Promise.all(meetings.map((row) => readDraft(accountId, row.id)))).filter(
    (row): row is Draft => !!row,
  );
}
/** 同一会议串行写入，成功后才清除待保存标记。 */
export function saveDraft(draft: Draft): Promise<Draft> {
  const cacheKey = key(draft.accountId, draft.meeting.id);
  const operation = (queues.get(cacheKey) ?? Promise.resolve())
    .catch(() => {})
    .then(async () => {
      const head = heads.get(cacheKey);
      if (head && draft.version < head.version) {
        const saved = await readDraft(draft.accountId, draft.meeting.id);
        if (!saved) throw new Error("会议已删除。");
        return saved;
      }
      const server = await saveMeeting(
        draft.accountId,
        draft,
        head?.revision ?? draft.meeting.revision,
      );
      heads.set(cacheKey, { revision: server.meeting.revision, version: draft.version });
      return { ...localDraft(server), version: draft.version, temporary: draft.temporary };
    });
  queues.set(cacheKey, operation);
  void operation
    .finally(() => {
      if (queues.get(cacheKey) === operation) queues.delete(cacheKey);
    })
    .catch(() => {});
  return operation;
}
export async function removeDraft(accountId: number, id: string) {
  const cacheKey = key(accountId, id);
  await queues.get(cacheKey)?.catch(() => {});
  await deleteMeeting(accountId, id);
  heads.delete(cacheKey);
}
export async function replaceFromServer(workspace: Workspace, force = false) {
  if (force) {
    const fresh = await readDraft(workspace.meeting.owner_id, workspace.meeting.id);
    if (!fresh) throw new Error("会议不存在或已删除。");
    return {
      ...fresh,
      version: (heads.get(key(workspace.meeting.owner_id, workspace.meeting.id))?.version ?? 0) + 1,
    };
  }
  const draft = localDraft(workspace);
  draft.version = (heads.get(key(draft.accountId, draft.meeting.id))?.version ?? 0) + 1;
  return saveDraft(draft);
}

/** 接收已提交的服务器状态，不再次发送保存请求。 */
export function acceptServerWorkspace(workspace: Workspace, version: number): Draft {
  const draft = { ...localDraft(workspace), version };
  heads.set(key(draft.accountId, draft.meeting.id), {
    revision: workspace.meeting.revision,
    version,
  });
  return draft;
}
