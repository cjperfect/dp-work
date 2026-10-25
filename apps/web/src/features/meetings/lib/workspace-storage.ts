import type { SyncPayload, Workspace } from "@/apis/meetings";
export type Draft = Workspace & {
  accountId: number;
  version: number;
  dirtyControls: boolean;
  dirtyMinutes: boolean;
  dirtyEntries: string[];
  temporary: { speaker: string; text: string };
  flight: { version: number; payload: SyncPayload } | null;
  error: string | null;
};
export const isPending = (draft: Draft) =>
  draft.dirtyControls || draft.dirtyMinutes || draft.dirtyEntries.length > 0 || !!draft.flight;
let connection: Promise<IDBDatabase> | null = null;
function db() {
  if (!connection)
    connection = new Promise<IDBDatabase>((resolve, reject) => {
      const request = indexedDB.open("dp-meeting-workspaces", 2);
      request.onupgradeneeded = () => {
        const store = request.result.objectStoreNames.contains("drafts")
          ? request.transaction!.objectStore("drafts")
          : request.result.createObjectStore("drafts", { keyPath: ["accountId", "meeting.id"] });
        if (!store.indexNames.contains("account")) store.createIndex("account", "accountId");
      };
      request.onsuccess = () => {
        request.result.onversionchange = () => {
          request.result.close();
          connection = null;
        };
        resolve(request.result);
      };
      request.onerror = () => {
        connection = null;
        reject(new Error("无法打开会议本地存储。"));
      };
      request.onblocked = () => {
        connection = null;
        reject(new Error("请关闭其他会议页面后重试本地保存。"));
      };
    });
  return connection;
}
async function transaction<T>(
  run: (store: IDBObjectStore, done: (value: T) => void) => void,
  mode: IDBTransactionMode = "readwrite",
): Promise<T> {
  const database = await db();
  return new Promise<T>((resolve, reject) => {
    const tx = database.transaction("drafts", mode);
    let value: T;
    tx.oncomplete = () => resolve(value);
    tx.onabort = () => reject(new Error("本地保存失败，请检查存储权限或空间。"));
    tx.onerror = () => {};
    try {
      run(tx.objectStore("drafts"), (result) => {
        value = result;
      });
    } catch (error) {
      tx.abort();
      reject(error);
    }
  });
}
export function localDraft(workspace: Workspace): Draft {
  return {
    ...workspace,
    accountId: workspace.meeting.owner_id,
    version: 0,
    dirtyControls: false,
    dirtyMinutes: false,
    dirtyEntries: [],
    temporary: { speaker: "", text: "" },
    flight: null,
    error: null,
  };
}
export const readDraft = (accountId: number, id: string) =>
  transaction<Draft | undefined>((store, done) => {
    const r = store.get([accountId, id]);
    r.onsuccess = () => done(r.result);
  }, "readonly");
export const listDrafts = (accountId: number) =>
  transaction<Draft[]>((store, done) => {
    const r = store.index("account").getAll(accountId);
    r.onsuccess = () => done((r.result as Draft[]).filter((d) => d.accountId === accountId));
  }, "readonly");
export const removeDraft = (accountId: number, id: string) =>
  transaction<void>((store, done) => {
    store.delete([accountId, id]);
    done();
  });
export function saveDraft(draft: Draft) {
  return transaction<Draft>((store, done) => {
    const request = store.get([draft.accountId, draft.meeting.id]);
    request.onsuccess = () => {
      const current = request.result as Draft | undefined;
      if (
        current &&
        (current.version > draft.version ||
          (current.version === draft.version && current.meeting.revision > draft.meeting.revision))
      ) {
        done(current);
        return;
      }
      const merged = {
        ...draft,
        meeting: {
          ...draft.meeting,
          revision: Math.max(draft.meeting.revision, current?.meeting.revision ?? 0),
        },
        flight: current ? current.flight : draft.flight,
      };
      store.put(merged);
      done(merged);
    };
  });
}
export function prepareFlight(accountId: number, id: string) {
  return transaction<Draft | undefined>((store, done) => {
    const r = store.get([accountId, id]);
    r.onsuccess = () => {
      const draft = r.result as Draft | undefined;
      if (!draft || !isPending(draft)) {
        done(draft);
        return;
      }
      if (!draft.flight) {
        draft.flight = {
          version: draft.version,
          payload: {
            expected_revision: draft.meeting.revision,
            sync_id: crypto.randomUUID(),
            segments: draft.segments
              .filter((row) => draft.dirtyEntries.includes(row.id))
              .slice(0, 200),
            ...(draft.dirtyMinutes ? { minutes: draft.minutes?.content ?? "" } : {}),
            ...(draft.dirtyControls
              ? {
                  controls: {
                    status: draft.meeting.status,
                    elapsed_ms: draft.meeting.elapsed_ms,
                    resumed_at: draft.meeting.resumed_at,
                  },
                }
              : {}),
          },
        };
        store.put(draft);
      }
      done(draft);
    };
  });
}
export function acknowledge(sent: Draft, server: Workspace) {
  return transaction<Draft | undefined>((store, done) => {
    const r = store.get([sent.accountId, sent.meeting.id]);
    r.onsuccess = () => {
      const current = r.result as Draft | undefined;
      if (!current) {
        done(undefined);
        return;
      }
      if (current.flight?.payload.sync_id !== sent.flight?.payload.sync_id) {
        done(current);
        return;
      }
      const newer = current.version > sent.flight!.version;
      const updated: Draft = newer
        ? { ...current, meeting: { ...current.meeting, revision: server.meeting.revision } }
        : {
            ...localDraft(server),
            version: current.version,
            temporary: current.temporary,
            dirtyEntries: current.dirtyEntries.filter(
              (id) => !sent.flight!.payload.segments.some((row) => row.id === id),
            ),
          };
      // 未发送的片段继续留在本地等待下一批，不能被服务器快照覆盖。
      if (!newer && updated.dirtyEntries.length) updated.segments = current.segments;
      updated.flight = null;
      updated.error = null;
      store.put(updated);
      done(updated);
    };
  });
}
export function replaceFromServer(workspace: Workspace, force = false) {
  return transaction<Draft>((store, done) => {
    const r = store.get([workspace.meeting.owner_id, workspace.meeting.id]);
    r.onsuccess = () => {
      const old = r.result as Draft | undefined;
      if (old && isPending(old) && !force) {
        done(old);
        return;
      }
      const fresh = {
        ...localDraft(workspace),
        temporary: old?.temporary ?? { speaker: "", text: "" },
        version: (old?.version ?? 0) + 1,
      };
      store.put(fresh);
      done(fresh);
    };
  });
}
