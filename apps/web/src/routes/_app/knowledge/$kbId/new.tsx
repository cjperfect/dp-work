import { NewKnowledgeDocumentPage } from "@/features/knowledge/components/knowledge-document-editor";
import { createFileRoute } from "@tanstack/react-router";

export const Route = createFileRoute("/_app/knowledge/$kbId/new")({
  staticData: { title: "新建文档" },
  component: NewKnowledgeDocumentPage,
});
