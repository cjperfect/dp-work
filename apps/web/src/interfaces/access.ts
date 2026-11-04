import type { AuthUser } from "./auth";

export type AccessRole = "admin" | "manager" | "member" | "viewer";
export interface CurrentAccess {
  role: string;
  permissions: string[];
}
export interface RolePolicy {
  role: AccessRole;
  permissions: string[];
  effective_permissions: string[];
}
export interface AccessCatalog {
  roles: RolePolicy[];
  permissions: string[];
}
export type ManagedUser = AuthUser;
export interface AccessManagementData {
  users: ManagedUser[];
  catalog: AccessCatalog;
}
