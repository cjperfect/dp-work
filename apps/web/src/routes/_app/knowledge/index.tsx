import { KnowledgePage } from "@/features/knowledge/components/knowledge-page";
import { createFileRoute } from "@tanstack/react-router";

export const Route = createFileRoute("/_app/knowledge/")({
  staticData: { title: "知识库" },
  component: KnowledgePage,
});
