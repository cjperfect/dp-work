import { GeneralAgentPage } from "@/features/agent/components/agent-route-page";
import { createFileRoute } from "@tanstack/react-router";

export const Route = createFileRoute("/_app/")({
  staticData: { title: "通用 Agent" },
  component: GeneralAgentPage,
});
