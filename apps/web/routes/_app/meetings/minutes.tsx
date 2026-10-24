import { createFileRoute, lazyRouteComponent } from "@tanstack/react-router";

export const Route = createFileRoute("/_app/meetings/minutes")({
  staticData: { title: "会议纪要" },
  component: lazyRouteComponent(
    () => import("@/features/meetings/components/meeting-minutes-page"),
    "MeetingMinutesPage",
  ),
});
