import { useState } from "react";
import { Check, ShieldCheck, Save } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  ACCESS_ROLE_DESCRIPTIONS,
  PERMISSION_GROUPS,
  PERMISSION_LABELS,
  roleLabel,
} from "@/constants/access";
import type { AccessCatalog, AccessRole, RolePolicy } from "@/interfaces/access";

export function RolePolicies({
  catalog,
  onSave,
}: {
  catalog: AccessCatalog;
  onSave: (role: AccessRole, permissions: string[], previous: string[]) => void;
}) {
  const [role, setRole] = useState<AccessRole>("member");
  const policy = catalog.roles.find((item) => item.role === role);
  return (
    <div className="grid gap-5 lg:grid-cols-[220px_minmax(0,1fr)]">
      <nav aria-label="选择角色" className="flex gap-2 overflow-x-auto lg:flex-col">
        {catalog.roles.map((item) => (
          <button
            key={item.role}
            type="button"
            aria-pressed={role === item.role}
            onClick={() => setRole(item.role)}
            className={`flex shrink-0 items-center gap-3 rounded-xl border px-4 py-3 text-left transition-colors lg:w-full ${role === item.role ? "border-primary/25 bg-primary/5" : "border-transparent hover:bg-muted"}`}
          >
            <ShieldCheck
              className={`size-4 ${role === item.role ? "text-primary" : "text-muted-foreground"}`}
            />
            <span className="flex-1">
              <span className="block text-sm font-medium">{roleLabel(item.role)}</span>
              <span className="mt-1 block text-xs text-muted-foreground">
                {item.effective_permissions.length} 项有效权限
              </span>
            </span>
            {role === item.role && <Check className="size-4 text-primary" />}
          </button>
        ))}
      </nav>
      {policy && (
        <PolicyEditor
          key={`${role}:${policy.permissions.join(",")}`}
          policy={policy}
          catalog={catalog}
          onSave={onSave}
        />
      )}
    </div>
  );
}

function PolicyEditor({
  policy,
  catalog,
  onSave,
}: {
  policy: RolePolicy;
  catalog: AccessCatalog;
  onSave: (role: AccessRole, permissions: string[], previous: string[]) => void;
}) {
  const [selected, setSelected] = useState(() => new Set(policy.permissions));
  const changed =
    selected.size !== policy.permissions.length || policy.permissions.some((p) => !selected.has(p));
  return (
    <section className="overflow-hidden rounded-xl border bg-background">
      <div className="flex flex-wrap items-start justify-between gap-4 border-b p-5">
        <div>
          <h2 className="font-semibold">{roleLabel(policy.role)}权限</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            {ACCESS_ROLE_DESCRIPTIONS[policy.role]}
          </p>
        </div>
        <div className="flex gap-2">
          {changed && (
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setSelected(new Set(policy.permissions))}
            >
              撤销更改
            </Button>
          )}
          <Button
            size="sm"
            disabled={!changed}
            onClick={() => onSave(policy.role, [...selected].sort(), policy.permissions)}
          >
            <Save className="size-3.5" />
            保存权限
          </Button>
        </div>
      </div>
      <p className="border-b bg-muted/30 px-5 py-3 text-xs leading-5 text-muted-foreground">
        每个角色独立授权，更改不会影响其他角色。系统会保留至少一位有效用户的权限管理能力。
      </p>
      <div className="divide-y">
        {PERMISSION_GROUPS.map((group) => (
          <div key={group.prefix} className="grid gap-4 p-5 xl:grid-cols-[140px_minmax(0,1fr)]">
            <div>
              <h3 className="text-sm font-medium">{group.label}</h3>
              <p className="mt-1 text-xs text-muted-foreground">{group.description}</p>
            </div>
            <div className="grid gap-2 sm:grid-cols-2">
              {catalog.permissions
                .filter((p) => p.startsWith(group.prefix))
                .map((permission) => {
                  return (
                    <label
                      key={permission}
                      className="flex cursor-pointer items-start gap-3 rounded-lg border px-3 py-3 hover:border-primary/40"
                    >
                      <input
                        type="checkbox"
                        aria-label={PERMISSION_LABELS[permission] ?? permission}
                        checked={selected.has(permission)}
                        className="mt-0.5 size-4 accent-primary"
                        onChange={(event) =>
                          setSelected((previous) => {
                            const next = new Set(previous);
                            if (event.target.checked) next.add(permission);
                            else next.delete(permission);
                            return next;
                          })
                        }
                      />
                      <span className="min-w-0 flex-1">
                        <span className="block text-xs font-medium">
                          {PERMISSION_LABELS[permission] ?? permission}
                        </span>
                        <span className="mt-1 block truncate font-mono text-[10px] text-muted-foreground">
                          {permission}
                        </span>
                      </span>
                    </label>
                  );
                })}
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}
