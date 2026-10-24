import { createFileRoute } from "@tanstack/react-router";
import { AppShell } from "@/components/layout/app-shell";

// 无路径布局：复用应用外壳，URL 中不会出现 _app。
export const Route = createFileRoute("/_app")({
  component: AppShell,
});
