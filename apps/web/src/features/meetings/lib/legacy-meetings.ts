import { useAuthStore } from "@/stores/auth";
import { importMeeting } from "@/apis/meetings";
import type { Draft } from "./workspace-storage";
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

const migrated = new Set<number>();
const running = new Map<number, Promise<void>>();
/** 仅迁移旧 IndexedDB 数据，成功后移除旧副本。 */
export function migrateLegacyMeetings(accountId: number): Promise<void> {
  if (useAuthStore.getState().user?.id !== accountId)
    return Promise.reject(new Error("登录状态已改变，请重新登录。"));
  if (typeof indexedDB === "undefined" || migrated.has(accountId)) return Promise.resolve();
  const existing = running.get(accountId);
  if (existing) return existing;
  const operation = (async () => {
    const drafts = await transaction<Draft[]>((store, done) => {
      const request = store.index("account").getAll(accountId);
      request.onsuccess = () => done(request.result);
    }, "readonly");
    for (const draft of drafts) {
      await importMeeting(accountId, draft);
      await transaction<void>((store, done) => {
        store.delete([accountId, draft.meeting.id]);
        done();
      });
    }
    migrated.add(accountId);
  })();
  running.set(accountId, operation);
  void operation.finally(() => running.delete(accountId)).catch(() => {});
  return operation;
}
