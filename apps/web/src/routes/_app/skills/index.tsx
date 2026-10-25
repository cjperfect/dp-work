import { SkillsPage } from "@/features/skills";
import { createFileRoute } from "@tanstack/react-router";

export const Route = createFileRoute("/_app/skills/")({
  staticData: { title: "技能安装" },
  component: SkillsPage,
});
