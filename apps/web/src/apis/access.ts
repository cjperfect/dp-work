import { http } from "@/lib/http";
import type { AccessCatalog, AccessRole, CurrentAccess, ManagedUser } from "@/interfaces/access";

export const getCurrentAccess = (signal?: AbortSignal) =>
  http.get<CurrentAccess>("/api/access/me", { signal });
export const getManagedUsers = (signal?: AbortSignal) =>
  http.get<ManagedUser[]>("/api/access/users", { signal });
export const getRolePolicies = (signal?: AbortSignal) =>
  http.get<AccessCatalog>("/api/access/roles", { signal });
export const updateUserRole = (userId: number, role: AccessRole, signal?: AbortSignal) =>
  http.put<ManagedUser>(`/api/access/users/${userId}/role`, { role }, { signal });
export const updateRolePermissions = (
  role: AccessRole,
  permissions: string[],
  signal?: AbortSignal,
) =>
  http.put<{ role: AccessRole; permissions: string[] }>(
    `/api/access/roles/${role}/permissions`,
    { permissions },
    { signal },
  );
