import { createFileRoute, lazyRouteComponent } from "@tanstack/react-router";

export const Route = createFileRoute("/_app/")({
  staticData: { title: "通用 Agent" },
  component: lazyRouteComponent(
    () => import("@/features/agent/components/agent-route-page"),
    "GeneralAgentPage",
  ),
});
