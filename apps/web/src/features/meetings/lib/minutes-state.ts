import type { Meeting } from "@/apis/meetings";

export type GenerationStatus = "idle" | "generating" | "ready" | "failed";
export function generationStatus(meeting: Meeting): GenerationStatus {
  if (meeting.generation_status) return meeting.generation_status;
  if (meeting.minutes_status === 0) return "generating";
  return "idle";
}
export function meetingCategory(meeting: Meeting): "pending" | "generating" | "archived" {
  if (meeting.status === "archived") return "archived";
  return generationStatus(meeting) === "idle" ? "pending" : "generating";
}
export function canEditMinutes(meeting: Meeting) {
  return meetingCategory(meeting) === "pending";
}
