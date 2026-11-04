import { createFileRoute, redirect, type ErrorComponentProps } from "@tanstack/react-router";
import { getAccessToken, useAuthStore } from "@/stores/auth";
import { requireManagementAccess } from "@/stores/access";
import { getManagedUsers, getRolePolicies } from "@/apis/access";
import { HttpError } from "@/lib/http";
import { PageError } from "@/components/layout/page-error";
import { AccessDenied } from "@/features/access/components/access-denied";
import { AccessManagementRoute } from "@/features/access/components/access-management-route";

export const Route = createFileRoute("/_app/admin/users")({
  staticData: { title: "用户与权限管理" },
  beforeLoad: async () => {
    if (!getAccessToken() || !useAuthStore.getState().user)
      throw redirect({ to: "/sign-in", search: { redirect: "/admin/users" }, replace: true });
    try {
      await requireManagementAccess();
    } catch (error) {
      if (error instanceof HttpError && error.status === 401)
        throw redirect({ to: "/sign-in", search: { redirect: "/admin/users" }, replace: true });
      throw error;
    }
  },
  loader: async ({ abortController }) => {
    const [users, catalog] = await Promise.all([
      getManagedUsers(abortController.signal),
      getRolePolicies(abortController.signal),
    ]);
    return { users, catalog };
  },
  errorComponent: (props: ErrorComponentProps) =>
    props.error instanceof HttpError && props.error.status === 403 ? (
      <AccessDenied />
    ) : (
      <PageError {...props} />
    ),
  component: AccessManagementRoute,
});
