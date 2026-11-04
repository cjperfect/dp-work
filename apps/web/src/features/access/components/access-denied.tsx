import { Link, useRouter } from "@tanstack/react-router";
import { ShieldOff } from "lucide-react";
import { Button } from "@/components/ui/button";

export function AccessDenied({
  error,
  title = "当前账号没有管理权限",
}: { error?: string | null; title?: string } = {}) {
  const router = useRouter();
  return (
    <section className="flex h-full min-h-80 flex-col items-center justify-center gap-4 p-8 text-center">
      <div className="rounded-2xl bg-muted p-4">
        <ShieldOff className="size-7 text-muted-foreground" />
      </div>
      <p className="text-xs font-medium tracking-widest text-muted-foreground">
        {error ? "权限核验" : "403 · 访问受限"}
      </p>
      <h1 className="text-xl font-semibold">{error ? "暂时无法核验访问权限" : title}</h1>
      <p className="max-w-sm text-sm leading-6 text-muted-foreground">
        {error ?? "请联系平台管理员确认当前账号的访问权限。"}
      </p>
      <div className="flex gap-2">
        <Button variant="outline" onClick={() => void router.invalidate()}>
          重新核验
        </Button>
        <Button nativeButton={false} render={<Link to="/" />}>
          返回工作区
        </Button>
      </div>
    </section>
  );
}
