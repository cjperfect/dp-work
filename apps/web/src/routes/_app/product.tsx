import { ProductAgentPage } from "@/features/agent/components/agent-route-page";
import { createFileRoute } from "@tanstack/react-router";

export const Route = createFileRoute("/_app/product")({
  staticData: { title: "产品 Agent" },
  component: ProductAgentPage,
});
