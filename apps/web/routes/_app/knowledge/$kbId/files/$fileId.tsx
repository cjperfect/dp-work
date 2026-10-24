import { createFileRoute, lazyRouteComponent } from "@tanstack/react-router";

export const Route = createFileRoute("/_app/knowledge/$kbId/files/$fileId")({
  staticData: { title: "文档预览" },
  component: lazyRouteComponent(
    () => import("@/features/knowledge/components/knowledge-page"),
    "KnowledgeFilePage",
  ),
});
