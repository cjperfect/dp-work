import type { Meeting } from "@/interfaces/meeting";
export type GenerationStatus = "idle" | "generating" | "ready" | "failed";
export function generationStatus(meeting: Meeting): GenerationStatus {
  if (meeting.generation_status) return meeting.generation_status;
  if (meeting.minutes_status === 0) return "generating";
  return "idle";
}
export function meetingCategory(meeting: Meeting): "pending" | "archived" {
  return meeting.status === "archived" ? "archived" : "pending";
}
export function showOriginalMeeting(meeting: Meeting) {
  return meeting.status !== "archived" && generationStatus(meeting) !== "ready";
}
export function canEditMinutes(meeting: Meeting) {
  const status = generationStatus(meeting);
  return meeting.status !== "archived" && status !== "generating" && status !== "failed";
}
