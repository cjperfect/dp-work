import { elapsed } from "@/apis/meetings";
import type { Draft } from "./workspace-storage";
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
