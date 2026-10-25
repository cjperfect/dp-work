import { MeetingSessionPage } from "@/features/meetings/components/meeting-session-page";
import { createFileRoute } from "@tanstack/react-router";

export const Route = createFileRoute("/_app/meetings/active")({
  validateSearch: (search: Record<string, unknown>): { id?: string } => ({
    id: typeof search.id === "string" ? search.id : undefined,
  }),
  staticData: { title: "进行中的会议" },
  component: MeetingSessionPage,
});
