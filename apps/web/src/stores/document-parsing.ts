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
