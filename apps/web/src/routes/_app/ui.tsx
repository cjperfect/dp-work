import { createFileRoute } from "@tanstack/react-router";
import { UiAgentPage } from "@/features/agent/components/agent-route-page";
export const Route = createFileRoute("/_app/ui")({
  staticData: { title: "UI Agent" },
  component: UiAgentPage,
});
