import { useLoaderData } from "@tanstack/react-router";
import { useAuthStore } from "@/stores/auth";
import { useAccessStore } from "@/stores/access";
import { AccessDenied } from "./access-denied";
import { AccessManagementPage } from "./access-management-page";

export function AccessManagementRoute() {
  const data = useLoaderData({ from: "/_app/admin/users" });
  const owner = useAuthStore((state) => state.user?.id);
  const canManage = useAccessStore(
    (state) => state.ownerId === owner && !!state.data?.permissions.includes("access:manage"),
  );
  const error = useAccessStore((state) => state.error);
  if (!canManage) return <AccessDenied error={error} />;
  return <AccessManagementPage key={owner} {...data} />;
}
