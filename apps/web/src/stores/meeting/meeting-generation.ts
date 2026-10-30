import type { Meeting } from "@/interfaces/meeting";
import { create } from "zustand";

import { useAuthStore } from "@/stores/auth";

type PendingTask = { ownerId: number; meetingId: string; taskId: string };
export const useMeetingGenerationStore = create<{ pending: Record<string, PendingTask> }>(() => ({
  pending: {},
}));
const notified = new Set<string>();
const key = (owner: number, task: string) => `${owner}:${task}`;

/** 记录已知正在生成的任务，切换路由后继续接收完成通知。 */
export function trackGenerations(meetings: Meeting[]) {
  const owner = useAuthStore.getState().user?.id;
  if (!owner) return;
  useMeetingGenerationStore.setState((state) => {
    let changed = false;
    const pending = { ...state.pending };
    for (const meeting of meetings) {
      const task = meeting.generation_task_id;
      if (
        meeting.owner_id !== owner ||
        meeting.generation_status !== "generating" ||
        !task ||
        notified.has(key(owner, task))
      )
        continue;
      for (const [id, old] of Object.entries(pending)) {
        if (old.ownerId === owner && old.meetingId === meeting.id && old.taskId !== task) {
          delete pending[id];
          changed = true;
        }
      }
      const id = key(owner, task);
      if (!pending[id]) {
        pending[id] = { ownerId: owner, meetingId: meeting.id, taskId: task };
        changed = true;
      }
    }
    return changed ? { pending } : state;
  });
}

/** 只通知已跟踪任务的结束状态，忽略历史记录和重连重复事件。 */
export function finishGenerations(meetings: Meeting[], snapshot = false): Meeting[] {
  const owner = useAuthStore.getState().user?.id;
  if (!owner) return [];
  const pending = { ...useMeetingGenerationStore.getState().pending };
  const completed: Meeting[] = [];
  let changed = false;
  for (const meeting of meetings) {
    const task = meeting.generation_task_id;
    if (
      meeting.owner_id !== owner ||
      !task ||
      !["ready", "failed"].includes(meeting.generation_status ?? "")
    )
      continue;
    const id = key(owner, task);
    if (!pending[id] || pending[id].meetingId !== meeting.id) continue;
    delete pending[id];
    changed = true;
    if (!notified.has(id)) {
      notified.add(id);
      completed.push(meeting);
    }
  }
  if (snapshot) {
    for (const [id, task] of Object.entries(pending)) {
      if (task.ownerId === owner && !meetings.some((row) => row.id === task.meetingId)) {
        delete pending[id];
        changed = true;
      }
    }
  }
  while (notified.size > 1000) notified.delete(notified.values().next().value!);
  if (changed) useMeetingGenerationStore.setState({ pending });
  return completed;
}

useAuthStore.subscribe((state, previous) => {
  if (state.user?.id !== previous.user?.id) {
    notified.clear();
    useMeetingGenerationStore.setState({ pending: {} });
  }
});

/** 主动删除会议时停止等待该会议的生成通知。 */
export function forgetGeneration(meetingId: string) {
  const owner = useAuthStore.getState().user?.id;
  useMeetingGenerationStore.setState((state) => ({
    pending: Object.fromEntries(
      Object.entries(state.pending).filter(
        ([, task]) => task.ownerId !== owner || task.meetingId !== meetingId,
      ),
    ),
  }));
}
