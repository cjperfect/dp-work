/**
 * 本地转写存储层（实时保存 + 待同步队列）
 *
 * 开发期（纯 Web）用浏览器 IndexedDB 实现，接口按 SQLite 语义设计；
 * Electron 阶段将实现替换为 better-sqlite3（Main 进程持有，Renderer 经 IPC 调用），
 * 调用方无需改动。一条 definite=true 分句 = 一条记录（一分句一行）。
 */

import { DB_NAME, DB_VERSION, STORE } from "@/constants/meeting-storage";
import { segmentId } from "@/features/meetings/utils/transcript";

export type TranscriptSegment = {
  /** 分句 id = 幂等键（meetingId + seq 派生） */
  id: string;
  meetingId: string;
  seq: number;
  speaker: string | null;
  text: string;
  startMs: number;
  /** 同步状态：pending = 待同步（outbox），synced = 已同步后端 */
  syncStatus: "pending" | "synced";
  attempt: number;
  createdAt: number;
};

const openDb = (): Promise<IDBDatabase> =>
  new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, DB_VERSION);
    req.onupgradeneeded = () => {
      const db = req.result;
      if (!db.objectStoreNames.contains(STORE)) {
        const store = db.createObjectStore(STORE, { keyPath: "id" });
        store.createIndex("meeting_seq", ["meetingId", "seq"], { unique: true });
        store.createIndex("sync_status", ["meetingId", "syncStatus"], { unique: false });
      }
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });

const idbRequest = <T>(req: IDBRequest<T>): Promise<T> =>
  new Promise((resolve, reject) => {
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });

/** 追加保存新分句（append-only：只增不覆盖；同 id 已存在则跳过） */
export async function saveSegments(
  meetingId: string,
  rows: { speaker: string | null; text: string; startMs: number }[],
  startSeq: number,
): Promise<number> {
  const db = await openDb();
  try {
    const tx = db.transaction(STORE, "readwrite");
    const store = tx.objectStore(STORE);
    let written = 0;
    rows.forEach((row, i) => {
      const seq = startSeq + i;
      const seg: TranscriptSegment = {
        id: segmentId(meetingId, seq),
        meetingId,
        seq,
        speaker: row.speaker,
        text: row.text,
        startMs: row.startMs,
        syncStatus: "pending",
        attempt: 0,
        createdAt: Date.now(),
      };
      store.add(seg); // add 遇重复 id 自动忽略（append-only 幂等）
      written += 1;
    });
    await new Promise<void>((resolve, reject) => {
      tx.oncomplete = () => resolve();
      tx.onerror = () => reject(tx.error);
    });
    return written;
  } finally {
    db.close();
  }
}

/** 按会议取全部分句（按 seq 升序） */
export async function listSegments(meetingId: string): Promise<TranscriptSegment[]> {
  const db = await openDb();
  try {
    const tx = db.transaction(STORE, "readonly");
    const store = tx.objectStore(STORE);
    const idx = store.index("meeting_seq");
    const range = IDBKeyRange.bound([meetingId, 0], [meetingId, Number.MAX_SAFE_INTEGER]);
    const rows = await idbRequest(idx.getAll(range));
    return rows.sort((a, b) => a.seq - b.seq);
  } finally {
    db.close();
  }
}

/** 待同步队列（outbox）：pending 分句 */
export async function pendingSegments(meetingId: string): Promise<TranscriptSegment[]> {
  const db = await openDb();
  try {
    const tx = db.transaction(STORE, "readonly");
    const store = tx.objectStore(STORE);
    const idx = store.index("sync_status");
    const range = IDBKeyRange.only([meetingId, "pending"]);
    const rows = await idbRequest(idx.getAll(range));
    return rows.sort((a, b) => a.seq - b.seq);
  } finally {
    db.close();
  }
}

/** 标记已同步（同步成功后调用） */
export async function markSynced(meetingId: string, ids: string[]): Promise<void> {
  const db = await openDb();
  try {
    const tx = db.transaction(STORE, "readwrite");
    const store = tx.objectStore(STORE);
    for (const id of ids) {
      const seg = await idbRequest(store.get(id));
      if (seg && seg.meetingId === meetingId) {
        store.put({ ...seg, syncStatus: "synced", attempt: seg.attempt });
      }
    }
    await new Promise<void>((resolve, reject) => {
      tx.oncomplete = () => resolve();
      tx.onerror = () => reject(tx.error);
    });
  } finally {
    db.close();
  }
}

/** 会议内最大 seq（新会议从 0 开始） */
export async function maxSeq(meetingId: string): Promise<number> {
  const rows = await listSegments(meetingId);
  return rows.length ? rows[rows.length - 1].seq : -1;
}

/** 结束会议 / 新会议：清空本地分句 */
export async function clearMeeting(meetingId: string): Promise<void> {
  const db = await openDb();
  try {
    const tx = db.transaction(STORE, "readwrite");
    const store = tx.objectStore(STORE);
    const idx = store.index("meeting_seq");
    const range = IDBKeyRange.bound([meetingId, 0], [meetingId, Number.MAX_SAFE_INTEGER]);
    const ids = await idbRequest(idx.getAllKeys(range));
    for (const id of ids) void store.delete(id);
    await new Promise<void>((resolve, reject) => {
      tx.oncomplete = () => resolve();
      tx.onerror = () => reject(tx.error);
    });
  } finally {
    db.close();
  }
}
