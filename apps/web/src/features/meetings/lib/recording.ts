import type { Draft } from "./workspace-storage";
import { elapsed } from "@/apis/meetings";

export function confirmTemporary(draft: Draft): Draft {
  const text = draft.temporary.text.trim();
  if (!text) return draft;
  const entry = {
    id: crypto.randomUUID(),
    seq: Math.max(-1, ...draft.segments.map((row) => row.seq)) + 1,
    speaker: draft.temporary.speaker.trim() || null,
    text,
    start_ms: Math.floor(elapsed(draft.meeting)),
  };
  return {
    ...draft,
    segments: [...draft.segments, entry],
    dirtyEntries: [...draft.dirtyEntries, entry.id],
    temporary: { ...draft.temporary, text: "" },
  };
}
export function control(draft: Draft, status: "active" | "paused" | "ended"): Draft {
  const now = Date.now();
  return {
    ...draft,
    dirtyControls: true,
    meeting: {
      ...draft.meeting,
      status,
      elapsed_ms: Math.floor(elapsed(draft.meeting, now)),
      resumed_at: status === "active" ? new Date(now).toISOString() : null,
    },
  };
}

/** 修改原始转写正文，保留片段标识、说话人和时间。 */
export function updateTranscriptText(draft: Draft, id: string, text: string): Draft {
  const entry = draft.segments.find((row) => row.id === id);
  if (!entry || entry.text === text) return draft;
  return {
    ...draft,
    segments: draft.segments.map((row) =>
      row.id === id ? { ...row, text, revision: (row.revision ?? 1) + 1 } : row,
    ),
    dirtyEntries: [...new Set([...draft.dirtyEntries, id])],
  };
}
