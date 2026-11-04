import { useState } from "react";
import { Search, UserRoundCog } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ACCESS_ROLE_LABELS, roleLabel } from "@/constants/access";
import type { AccessRole, ManagedUser } from "@/interfaces/access";

export function UserTable({
  users,
  currentId,
  onEdit,
}: {
  users: ManagedUser[];
  currentId?: number;
  onEdit: (user: ManagedUser) => void;
}) {
  const [query, setQuery] = useState("");
  const [role, setRole] = useState("");
  const needle = query.trim().toLocaleLowerCase();
  const filtered = users.filter(
    (user) =>
      (!role || user.role === role) &&
      `${user.username} ${user.department}`.toLocaleLowerCase().includes(needle),
  );
  return (
    <section className="overflow-hidden rounded-xl border bg-background">
      <div className="flex flex-wrap items-center gap-3 border-b p-4">
        <div className="relative min-w-52 flex-1 sm:max-w-sm">
          <Search className="absolute top-2.5 left-3 size-4 text-muted-foreground" />
          <Input
            aria-label="搜索用户名或部门"
            placeholder="搜索用户名或部门…"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            className="pl-9"
          />
        </div>
        <select
          aria-label="按角色筛选"
          className="h-9 rounded-md border bg-background px-3 text-sm"
          value={role}
          onChange={(event) => setRole(event.target.value)}
        >
          <option value="">全部角色</option>
          {Object.entries(ACCESS_ROLE_LABELS).map(([key, label]) => (
            <option key={key} value={key}>
              {label}
            </option>
          ))}
        </select>
        <span className="ml-auto text-xs text-muted-foreground" aria-live="polite">
          共 {filtered.length} 位用户
        </span>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead className="bg-muted/40 text-xs text-muted-foreground">
            <tr>
              {["用户", "部门", "角色", "账号状态", "注册时间", "操作"].map((title) => (
                <th key={title} className="px-5 py-3 font-medium whitespace-nowrap">
                  {title}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y">
            {filtered.map((user) => (
              <tr key={user.id} className="transition-colors hover:bg-muted/25">
                <td className="px-5 py-4">
                  <div className="flex items-center gap-3">
                    <span className="flex size-9 shrink-0 items-center justify-center rounded-full bg-muted text-xs font-semibold">
                      {user.username.slice(0, 2).toUpperCase()}
                    </span>
                    <div>
                      <div className="flex items-center gap-2 font-medium">
                        {user.username}
                        {user.id === currentId && (
                          <span className="rounded bg-muted px-1.5 py-0.5 text-[10px] font-normal text-muted-foreground">
                            当前账号
                          </span>
                        )}
                      </div>
                      <div className="mt-0.5 text-xs text-muted-foreground">ID {user.id}</div>
                    </div>
                  </div>
                </td>
                <td className="px-5 py-4 whitespace-nowrap">
                  {user.department === "unassigned" ? "未分配" : user.department}
                </td>
                <td className="px-5 py-4 whitespace-nowrap">
                  <RoleBadge role={user.role} />
                </td>
                <td className="px-5 py-4">
                  <span className="inline-flex items-center gap-1.5 whitespace-nowrap text-xs">
                    <span
                      className={`size-1.5 rounded-full ${user.status === 0 ? "bg-emerald-500" : "bg-amber-500"}`}
                    />
                    {user.status === 0 ? "正常" : "已冻结"}
                  </span>
                </td>
                <td className="px-5 py-4 text-xs whitespace-nowrap text-muted-foreground">
                  {new Date(user.created_at).toLocaleDateString("zh-CN")}
                </td>
                <td className="px-5 py-4">
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => onEdit(user)}
                    aria-label={`调整 ${user.username} 的角色`}
                  >
                    <UserRoundCog className="size-3.5" />
                    调整角色
                  </Button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {filtered.length === 0 && (
          <div className="px-6 py-16 text-center">
            <Search className="mx-auto mb-3 size-6 text-muted-foreground" />
            <p className="font-medium">没有找到匹配的用户</p>
            <p className="mt-1 text-sm text-muted-foreground">试试其他用户名、部门或角色。</p>
          </div>
        )}
      </div>
    </section>
  );
}

export function RoleBadge({ role }: { role: AccessRole | string }) {
  return (
    <span
      className={`inline-flex rounded-md border px-2 py-1 text-xs ${role === "admin" ? "border-primary/20 bg-primary/10 text-primary" : "border-border bg-muted/30 text-foreground"}`}
    >
      {roleLabel(role)}
    </span>
  );
}
