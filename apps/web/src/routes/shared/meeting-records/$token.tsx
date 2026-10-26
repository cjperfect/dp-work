import { createFileRoute } from "@tanstack/react-router";
import { SharedRecordPage } from "@/features/meetings/components/shared-record-page";
export const Route = createFileRoute("/shared/meeting-records/$token")({
  component: SharedRecordPage,
});
