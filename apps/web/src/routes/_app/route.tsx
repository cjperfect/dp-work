import { redirect, type ErrorComponentProps } from "@tanstack/react-router";
import { getAccessToken, useAuthStore, safeRedirect } from "@/stores/auth";
import { requirePermissions } from "@/stores/access";
import { pagePermissions } from "@/features/access/lib/page-permissions";
import { AccessDenied } from "@/features/access/components/access-denied";
import { PageError } from "@/components/layout/page-error";
import { HttpError } from "@/lib/http";
import { createFileRoute } from "@tanstack/react-router";
import { MeetingSync } from "@/features/meetings/components/meeting-sync";
import { AppShell } from "@/components/layout/app-shell";

// 无路径布局：加载应用外壳。
export const Route = createFileRoute("/_app")({
  beforeLoad: async ({ location }) => {
    const permissions = pagePermissions(location.pathname);
    if (!permissions.length) return;
    const login = () =>
      redirect({
        to: "/sign-in",
        search: { redirect: safeRedirect(location.href) },
        replace: true,
      });
    if (!getAccessToken() || !useAuthStore.getState().user) throw login();
    try {
      await requirePermissions(...permissions);
    } catch (error) {
      if (error instanceof HttpError && error.status === 401) throw login();
      throw error;
    }
  },
  errorComponent: (props: ErrorComponentProps) =>
    props.error instanceof HttpError && props.error.status === 403 ? (
      <AccessDenied title="当前账号没有此页面的访问权限" />
    ) : (
      <PageError {...props} />
    ),
  component: () => (
    <>
      <MeetingSync />
      <AppShell />
    </>
  ),
});
