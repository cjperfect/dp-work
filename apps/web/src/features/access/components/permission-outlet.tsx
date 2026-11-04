import { Outlet, useLocation } from "@tanstack/react-router";
import { usePermission } from "../hooks/use-permission";
import { useAccessStore } from "@/stores/access";
import { pagePermissions } from "../lib/page-permissions";
import { AccessDenied } from "./access-denied";

export function PermissionOutlet() {
  const path = useLocation({ select: (location) => location.pathname });
  const permissions = pagePermissions(path);
  const allowed = usePermission(...permissions);
  const error = useAccessStore((state) => state.error);
  if (permissions.length && !allowed)
    return <AccessDenied error={error} title="当前账号没有此页面的访问权限" />;
  return <Outlet />;
}
