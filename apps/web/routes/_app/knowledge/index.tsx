import { createFileRoute, lazyRouteComponent } from "@tanstack/react-router";

export const Route = createFileRoute("/_app/knowledge/")({
  staticData: { title: "知识库" },
  component: lazyRouteComponent(
    () => import("@/features/knowledge/components/knowledge-page"),
    "KnowledgePage",
  ),
});
