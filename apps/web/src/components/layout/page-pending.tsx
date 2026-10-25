import { Loader2 } from "lucide-react";

export function PagePending() {
  return (
    <main
      className="flex min-h-dvh items-center justify-center gap-3 bg-background px-6 text-sm text-muted-foreground"
      role="status"
    >
      <Loader2 className="size-4 animate-spin" aria-hidden="true" />
      正在加载页面…
    </main>
  );
}
