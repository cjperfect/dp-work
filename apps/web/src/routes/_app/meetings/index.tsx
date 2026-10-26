import { MeetingsPage } from "@/features/meetings/components/meetings-page";
import { createFileRoute } from "@tanstack/react-router";

export const Route = createFileRoute("/_app/meetings/")({
  validateSearch: (search: Record<string, unknown>): { view?: "pending" | "archived" } => ({
    view:
      search.view === "generating"
        ? "pending"
        : search.view === "pending" || search.view === "archived"
          ? search.view
          : undefined,
  }),
  staticData: { title: "开始会议" },
  component: MeetingsPage,
});
