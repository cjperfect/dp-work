import { KnowledgeFilePage } from "@/features/knowledge/components/knowledge-page";
import { createFileRoute } from "@tanstack/react-router";

export const Route = createFileRoute("/_app/knowledge/$kbId/files/$fileId")({
  staticData: { title: "文档预览" },
  component: KnowledgeFilePage,
});
