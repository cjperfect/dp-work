import { createFileRoute } from "@tanstack/react-router";
import { MeetingSync } from "@/features/meetings/components/meeting-sync";
import { AppShell } from "@/components/layout/app-shell";

// 无路径布局：加载应用外壳。
export const Route = createFileRoute("/_app")({
  component: () => (
    <>
      <MeetingSync />
      <AppShell />
    </>
  ),
});
