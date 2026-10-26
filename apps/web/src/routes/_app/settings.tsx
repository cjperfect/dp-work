import { createFileRoute } from "@tanstack/react-router";
import { SettingsPage } from "@/features/settings";

export const Route = createFileRoute("/_app/settings")({
  staticData: { title: "设置" },
  component: SettingsPage,
});
