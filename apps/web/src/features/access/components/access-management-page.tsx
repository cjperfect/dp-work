import { useEffect, useRef, useState } from "react";
import { useRouter, useRouterState } from "@tanstack/react-router";
import { Loader2, RefreshCw, ShieldCheck, UsersRound } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { updateUserRole, updateRolePermissions } from "@/apis/access";
import { ACCESS_ROLE_LABELS, PERMISSION_LABELS, roleLabel } from "@/constants/access";
import { getAccessToken, useAuthStore } from "@/stores/auth";
import { refreshAccess, useAccessStore } from "@/stores/access";
import { HttpError } from "@/lib/http";
import type { AccessManagementData, AccessRole, ManagedUser } from "@/interfaces/access";
import { UserTable } from "./user-table";
import { RolePolicies } from "./role-policies";

type Change =
  | { kind: "user"; user: ManagedUser; role: AccessRole }
  | { kind: "policy"; role: AccessRole; permissions: string[]; previous: string[] };

export function AccessManagementPage({ users, catalog }: AccessManagementData) {
  const currentRole = useAccessStore((state) => state.data?.role);
  const currentId = useAuthStore((state) => state.user?.id);
  const router = useRouter();
  const refreshing = useRouterState({ select: (state) => state.isLoading });
  const [change, setChange] = useState<Change | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const controller = useRef<AbortController | null>(null);
  useEffect(() => {
    const current = new AbortController();
    controller.current = current;
    return () => current.abort();
  }, []);
  function propose(next: Change) {
    setError(null);
    setChange(next);
  }
  async function save() {
    if (!change || saving || controller.current?.signal.aborted) return;
    const token = getAccessToken();
    const signal = controller.current?.signal;
    const current = () => !signal?.aborted && getAccessToken() === token;
    setSaving(true);
    setError(null);
    try {
      if (change.kind === "user") await updateUserRole(change.user.id, change.role, signal);
      else await updateRolePermissions(change.role, change.permissions, signal);
    } catch (cause) {
      if (!current()) return;
      setError(cause instanceof Error ? cause.message : "保存失败，请重试。");
      if (cause instanceof HttpError && cause.status === 403) void refreshAccess().catch(() => {});
      setSaving(false);
      return;
    }
    if (!current()) return;
    setChange(null);
    setSaving(false);
    toast.success(change.kind === "user" ? "用户角色已更新" : "角色权限已更新");
    try {
      const access = await refreshAccess();
      if (!current()) return;
      if (!access.permissions.includes("access:manage"))
        await router.navigate({ to: "/", replace: true });
      else await router.invalidate();
    } catch {
      if (current()) toast.error("更改已保存，暂时无法刷新页面，请重试。");
    }
  }
  return (
    <main className="h-full overflow-y-auto bg-muted/15">
      <div className="mx-auto max-w-7xl space-y-6 p-5 md:p-8">
        <header className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <div className="mb-2 flex items-center gap-2 text-xs font-medium text-muted-foreground">
              <ShieldCheck className="size-3.5 text-primary" />
              平台管理
            </div>
            <h1 className="text-2xl font-semibold tracking-tight">用户与权限</h1>
            <p className="mt-2 text-sm text-muted-foreground">
              管理团队账号与操作权限，让每位成员各司其职。
            </p>
          </div>
          <Button
            variant="outline"
            disabled={refreshing || saving}
            onClick={() => void router.invalidate()}
          >
            <RefreshCw className={`size-4 ${refreshing ? "animate-spin" : ""}`} />
            刷新
          </Button>
        </header>
        <Tabs defaultValue="users" className="space-y-5">
          <div className="flex flex-wrap items-center justify-between gap-3 border-b pb-4">
            <TabsList>
              <TabsTrigger value="users">
                <UsersRound />
                用户管理
                <span className="ml-1 rounded bg-background/60 px-1.5 text-xs">{users.length}</span>
              </TabsTrigger>
              <TabsTrigger value="roles">
                <ShieldCheck />
                角色权限
              </TabsTrigger>
            </TabsList>
            <p className="text-xs text-muted-foreground">
              角色控制操作权限，资源访问仍以实际授权为准。
            </p>
          </div>
          <TabsContent value="users">
            <UserTable
              users={users}
              currentId={currentId}
              onEdit={(user) => propose({ kind: "user", user, role: user.role as AccessRole })}
            />
          </TabsContent>
          <TabsContent value="roles">
            <RolePolicies
              catalog={catalog}
              onSave={(role, permissions, previous) =>
                propose({ kind: "policy", role, permissions, previous })
              }
            />
          </TabsContent>
        </Tabs>
      </div>
      <Dialog
        open={change !== null}
        onOpenChange={(open) => {
          if (!open && !saving) setChange(null);
        }}
      >
        <DialogContent showCloseButton={!saving}>
          <DialogHeader>
            <DialogTitle>
              {change?.kind === "user" ? "调整用户角色" : "确认更新角色权限"}
            </DialogTitle>
            <DialogDescription>
              {change?.kind === "user"
                ? `为 ${change.user.username} 分配新的平台角色。`
                : `更改将影响所有${roleLabel(change?.role ?? "")}，并在下次权限检查时生效。`}
            </DialogDescription>
          </DialogHeader>
          {change?.kind === "user" && (
            <div className="space-y-3 py-2">
              <label htmlFor="assigned-role" className="text-sm font-medium">
                角色
              </label>
              <Select
                value={change.role}
                onValueChange={(value) => {
                  if (value) setChange({ ...change, role: value as AccessRole });
                }}
                disabled={saving}
              >
                <SelectTrigger id="assigned-role" className="w-full">
                  <SelectValue>{roleLabel(change.role)}</SelectValue>
                </SelectTrigger>
                <SelectContent>
                  {Object.entries(ACCESS_ROLE_LABELS).map(([role, label]) => (
                    <SelectItem key={role} value={role}>
                      {label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              {change.user.id === currentId && change.role !== "admin" && (
                <p className="rounded-lg bg-amber-500/10 p-3 text-xs leading-5 text-amber-700 dark:text-amber-300">
                  你正在调整自己的角色，保存后可能退出管理页面。系统会保护最后一个有效管理员。
                </p>
              )}
            </div>
          )}
          {change?.kind === "policy" && (
            <div className="max-h-64 space-y-2 overflow-y-auto rounded-lg bg-muted/40 p-3 text-xs">
              {change.permissions
                .filter((p) => !change.previous.includes(p))
                .map((p) => (
                  <p key={p} className="text-emerald-700 dark:text-emerald-300">
                    ＋ 授予 {PERMISSION_LABELS[p] ?? p}
                  </p>
                ))}
              {change.previous
                .filter((p) => !change.permissions.includes(p))
                .map((p) => (
                  <p key={p} className="text-destructive">
                    － 撤销 {PERMISSION_LABELS[p] ?? p}
                  </p>
                ))}
            </div>
          )}
          {change?.kind === "policy" &&
            change.role === currentRole &&
            !change.permissions.includes("access:manage") && (
              <p className="rounded-lg bg-amber-500/10 p-3 text-xs leading-5 text-amber-700 dark:text-amber-300">
                你将撤销当前角色的权限管理能力，保存后会退出管理页面。若没有其他有效用户能够管理权限，系统将拒绝此次更改。
              </p>
            )}
          {error && (
            <p role="alert" className="rounded-lg bg-destructive/10 p-3 text-sm text-destructive">
              {error}
            </p>
          )}
          <DialogFooter>
            <Button variant="outline" disabled={saving} onClick={() => setChange(null)}>
              取消
            </Button>
            <Button
              disabled={saving || (change?.kind === "user" && change.role === change.user.role)}
              onClick={() => void save()}
            >
              {saving && <Loader2 className="size-4 animate-spin" />}
              {saving ? "保存中…" : "确认保存"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </main>
  );
}
