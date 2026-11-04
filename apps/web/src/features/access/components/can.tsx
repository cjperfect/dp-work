import type { ReactNode } from "react";
import { usePermission } from "../hooks/use-permission";

export function Can({
  permission,
  children,
}: {
  permission: string | string[];
  children: ReactNode;
}) {
  const allowed = usePermission(...(typeof permission === "string" ? [permission] : permission));
  return allowed ? children : null;
}
