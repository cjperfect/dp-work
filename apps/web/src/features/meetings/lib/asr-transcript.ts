import type { WsAsrTranscript } from "@dp-work/protocols/asr";
import type { Draft } from "./workspace-storage";
/** 按片段 ID 和版本合并转写，确认片段不被临时结果覆盖。 */
export function applyAsrTranscript(draft: Draft, message: WsAsrTranscript): Draft {
  if (draft.meeting.id !== message.meetingId) return draft;
  const segment = message.segment;
  const old = draft.segments.find((row) => row.id === segment.id);
  const speaker = segment.speakerId ? `说话人 ${segment.speakerId.replace(/^speaker-/, "")}` : null;
  if (!segment.isFinal) {
    if (
      old ||
      (draft.temporary.id === segment.id && (draft.temporary.revision ?? 0) >= segment.revision)
    )
      return draft;
    if (draft.segments.some((row) => row.seq >= segment.seq)) return draft;
    if (draft.temporary.seq !== undefined && draft.temporary.seq > segment.seq) return draft;
    return {
      ...draft,
      temporary: {
        id: segment.id,
        seq: segment.seq,
        revision: segment.revision,
        speaker: speaker ?? "",
        text: segment.text,
      },
    };
  }
  if (old && (old.revision ?? 0) >= segment.revision) return draft;
  const entry = {
    id: segment.id,
    seq: segment.seq,
    revision: segment.revision,
    speaker,
    text: segment.text,
    start_ms: segment.startMs,
    end_ms: segment.endMs,
  };
  return {
    ...draft,
    segments: [...draft.segments.filter((row) => row.id !== entry.id), entry].sort(
      (a, b) => a.seq - b.seq,
    ),
    dirtyEntries: [...new Set([...draft.dirtyEntries, entry.id])],
    temporary: draft.temporary.id === segment.id ? { speaker: "", text: "" } : draft.temporary,
  };
}
