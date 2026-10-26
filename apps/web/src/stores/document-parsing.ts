import type { DocumentParseState } from "@/features/knowledge/lib/parse-events";
import { useAuthStore } from "@/stores/auth";

const pending = new Map<string, string>();
const notified = new Set<string>();

/** 忽略历史任务；断线期间已完成的已知任务在重连时补通知。 */
export function consumeDocumentParseEvents(
  rows: DocumentParseState[],
  snapshot: boolean,
): DocumentParseState[] {
  const owner = useAuthStore.getState().user?.id;
  const completed: DocumentParseState[] = [];
  for (const row of rows) {
    if (row.owner_id !== owner) continue;
    const document = `${owner}:${row.id}`;
    const task = `${document}:${row.task_id}`;
    if (row.status === "queued" || row.status === "parsing") {
      if (!notified.has(task)) pending.set(document, task);
    } else if (row.status === "unparsed") {
      pending.delete(document);
    } else if (["parsed", "failed"].includes(row.status)) {
      const tracked = pending.get(document) === task;
      if (snapshot && !tracked) notified.add(task);
      pending.delete(document);
      if ((!snapshot || tracked) && !notified.has(task)) {
        notified.add(task);
        completed.push(row);
      }
    }
  }
  if (snapshot)
    for (const document of pending.keys()) {
      if (!rows.some((row) => `${owner}:${row.id}` === document)) pending.delete(document);
    }
  while (notified.size > 1000) notified.delete(notified.values().next().value!);
  return completed;
}

useAuthStore.subscribe((state, previous) => {
  if (state.user?.id !== previous.user?.id) {
    pending.clear();
    notified.clear();
  }
});

const vectorPending = new Map<string, string>();
const vectorNotified = new Set<string>();
/** 向量化复用解析事件连接，任务独立去重。 */
export function consumeDocumentVectorEvents(
  rows: DocumentParseState[],
  snapshot: boolean,
): DocumentParseState[] {
  const owner = useAuthStore.getState().user?.id;
  const completed: DocumentParseState[] = [];
  for (const row of rows) {
    if (row.owner_id !== owner) continue;
    const document = `${owner}:${row.id}`;
    if (!row.vector_task_id) {
      vectorPending.delete(document);
      continue;
    }
    const task = `${document}:${row.vector_task_id}`;
    if (row.vector_status === "queued" || row.vector_status === "indexing") {
      if (!vectorNotified.has(task)) vectorPending.set(document, task);
    } else if (row.vector_status === "indexed" || row.vector_status === "failed") {
      const tracked = vectorPending.get(document) === task;
      if (snapshot && !tracked) vectorNotified.add(task);
      vectorPending.delete(document);
      if ((!snapshot || tracked) && !vectorNotified.has(task)) {
        vectorNotified.add(task);
        completed.push(row);
      }
    }
  }
  if (snapshot)
    for (const id of vectorPending.keys()) {
      if (!rows.some((row) => `${owner}:${row.id}` === id)) vectorPending.delete(id);
    }
  while (vectorNotified.size > 1000) vectorNotified.delete(vectorNotified.values().next().value!);
  return completed;
}
useAuthStore.subscribe((state, previous) => {
  if (state.user?.id !== previous.user?.id) {
    vectorPending.clear();
    vectorNotified.clear();
  }
});
