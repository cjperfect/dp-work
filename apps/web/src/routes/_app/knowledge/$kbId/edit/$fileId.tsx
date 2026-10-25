import { EditKnowledgeDocumentPage } from "@/features/knowledge/components/knowledge-document-editor";
import { createFileRoute } from "@tanstack/react-router";

export const Route = createFileRoute("/_app/knowledge/$kbId/edit/$fileId")({
  staticData: { title: "编辑文档" },
  component: EditKnowledgeDocumentPage,
});
