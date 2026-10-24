import { createFileRoute, lazyRouteComponent } from "@tanstack/react-router";

export const Route = createFileRoute("/_app/product")({
  staticData: { title: "产品 Agent" },
  component: lazyRouteComponent(
    () => import("@/features/agent/components/agent-route-page"),
    "ProductAgentPage",
  ),
});
