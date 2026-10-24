import { createFileRoute, lazyRouteComponent } from "@tanstack/react-router";

export const Route = createFileRoute("/_app/skills/")({
  staticData: { title: "技能安装" },
  component: lazyRouteComponent(() => import("@/features/skills"), "SkillsPage"),
});
