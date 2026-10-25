import { MeetingMinutesPage } from "@/features/meetings/components/meeting-minutes-page";
import { createFileRoute } from "@tanstack/react-router";

export const Route = createFileRoute("/_app/meetings/minutes")({
  validateSearch: (search: Record<string, unknown>): { id?: string } => ({
    id: typeof search.id === "string" ? search.id : undefined,
  }),
  staticData: { title: "会议纪要" },
  component: MeetingMinutesPage,
});
