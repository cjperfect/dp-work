import { createFileRoute, lazyRouteComponent } from "@tanstack/react-router";

export const Route = createFileRoute("/_app/meetings/")({
  staticData: { title: "开始会议" },
  component: lazyRouteComponent(
    () => import("@/features/meetings/components/meetings-page"),
    "MeetingsPage",
  ),
});
