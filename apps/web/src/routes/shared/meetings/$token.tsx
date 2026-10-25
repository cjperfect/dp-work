import { SharedMinutesPage } from "@/features/meetings/components/shared-minutes-page";
import { createFileRoute } from "@tanstack/react-router";
export const Route = createFileRoute("/shared/meetings/$token")({
  component: SharedMinutesPage,
});
