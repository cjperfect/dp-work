import { redirect, type ErrorComponentProps, createFileRoute } from "@tanstack/react-router";
import { requirePermissions } from "@/stores/access";
import { HttpError } from "@/lib/http";
import { AccessDenied } from "@/features/access/components/access-denied";
import { PageError } from "@/components/layout/page-error";
import { SharedRecordPage } from "@/features/meetings/components/shared-record-page";
export const Route = createFileRoute("/shared/meeting-records/$token")({
  beforeLoad: async ({ location }) => {
    try {
      await requirePermissions("meeting:read");
    } catch (error) {
      if (error instanceof HttpError && error.status === 401)
        throw redirect({ to: "/sign-in", search: { redirect: location.href }, replace: true });
      throw error;
    }
  },
  errorComponent: (props: ErrorComponentProps) =>
    props.error instanceof HttpError && props.error.status === 403 ? (
      <AccessDenied title="当前账号没有会议查看权限" />
    ) : (
      <PageError {...props} />
    ),
  component: SharedRecordPage,
});
