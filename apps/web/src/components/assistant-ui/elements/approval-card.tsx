import { useId, type ReactNode } from "react";
import { Check, Loader2, ShieldCheck, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export type ApprovalState = "request" | "running" | "done" | "denied";

/** 按 assistant-ui ApprovalCard 的 standalone 接口适配现有 shadcn 主题。 */
export function ApprovalCard({
  state,
  title,
  subtitle,
  description,
  command,
  details,
  children,
  onAllowOnce,
  onDeny,
  statusLabel,
  disabled = false,
  className,
}: {
  state: ApprovalState;
  className?: string;
  title: string;
  subtitle?: string;
  description?: string;
  command?: string;
  details?: { label: string; value: string }[];
  children?: ReactNode;
  disabled?: boolean;
  onAllowOnce?(): void;
  onDeny?(): void;
  statusLabel?: string;
}) {
  const id = useId();
  return (
    <section
      data-slot="approval-card"
      aria-labelledby={id}
      className={cn("overflow-hidden rounded-xl border bg-card text-sm shadow-sm", className)}
    >
      <div className="flex gap-3 p-4">
        <span className="grid size-9 shrink-0 place-items-center rounded-lg bg-muted">
          <ShieldCheck className="size-4" />
        </span>
        <div className="min-w-0">
          <h3 id={id} className="font-medium">
            {title}
          </h3>
          {subtitle && <p className="mt-1 text-xs text-muted-foreground">{subtitle}</p>}
        </div>
      </div>
      {(description || command || details?.length || children) && (
        <div className="grid gap-3 px-4 pb-4">
          {description && <p className="text-xs leading-6 text-muted-foreground">{description}</p>}
          {command && (
            <pre className="max-h-64 overflow-auto whitespace-pre-wrap break-words rounded-lg bg-muted p-3 font-mono text-xs">
              {command}
            </pre>
          )}
          {details?.map((item) => (
            <div key={item.label} className="grid gap-1">
              <span className="text-xs text-muted-foreground">{item.label}</span>
              <pre className="max-h-64 overflow-auto whitespace-pre-wrap break-words rounded-lg bg-muted p-3 font-mono text-xs">
                {item.value}
              </pre>
            </div>
          ))}
          {children}
        </div>
      )}
      <div className="flex items-center justify-end gap-2 border-t bg-muted/20 px-4 py-3">
        {state === "request" ? (
          <>
            <Button variant="ghost" size="sm" disabled={disabled} onClick={onDeny}>
              拒绝
            </Button>
            <Button size="sm" disabled={disabled} onClick={onAllowOnce}>
              允许
            </Button>
          </>
        ) : (
          <p role="status" className="flex items-center gap-2 text-xs text-muted-foreground">
            {state === "running" ? (
              <Loader2 className="size-3.5 animate-spin" />
            ) : state === "denied" ? (
              <X className="size-3.5" />
            ) : (
              <Check className="size-3.5" />
            )}
            {statusLabel ??
              ({ running: "正在继续执行…", denied: "已拒绝", done: "已允许" } as const)[state]}
          </p>
        )}
      </div>
    </section>
  );
}
