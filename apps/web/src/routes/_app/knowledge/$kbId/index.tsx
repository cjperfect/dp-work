import { KnowledgeBaseDetailPage } from "@/features/knowledge/components/knowledge-page";
import { createFileRoute } from "@tanstack/react-router";

export const Route = createFileRoute("/_app/knowledge/$kbId/")({
  staticData: { title: "知识库详情" },
  component: KnowledgeBaseDetailPage,
});
