import { createFileRoute, lazyRouteComponent } from "@tanstack/react-router";

export const Route = createFileRoute("/_app/knowledge/$kbId/")({
  staticData: { title: "知识库详情" },
  component: lazyRouteComponent(
    () => import("@/features/knowledge/components/knowledge-page"),
    "KnowledgeBaseDetailPage",
  ),
});
