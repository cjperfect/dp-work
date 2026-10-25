import { Link, useRouter, type ErrorComponentProps } from "@tanstack/react-router";
import { Button } from "@/components/ui/button";

export function PageError({ error }: ErrorComponentProps) {
  const router = useRouter();
  return (
    <main className="flex min-h-dvh flex-col items-center justify-center gap-4 px-6 text-center">
      <h1 className="text-lg font-semibold">页面加载失败</h1>
      <p className="text-sm text-muted-foreground">
        {error instanceof Error ? error.message : "请稍后重试。"}
      </p>
      <Button onClick={() => void router.invalidate()}>重试</Button>
      <Link to="/sign-in" search={{ redirect: "/" }} className="text-sm underline">
        返回登录
      </Link>
    </main>
  );
}
