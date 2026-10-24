import { createFileRoute, lazyRouteComponent } from "@tanstack/react-router";

export const Route = createFileRoute("/_app/meetings/active")({
  staticData: { title: "进行中的会议" },
  component: lazyRouteComponent(
    () => import("@/features/meetings/components/meeting-session-page"),
    "MeetingSessionPage",
  ),
});
