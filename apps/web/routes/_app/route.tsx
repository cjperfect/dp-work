import {
  createFileRoute,
  Link,
  redirect,
  useRouter,
  type ErrorComponentProps,
} from "@tanstack/react-router";
import { AppShell } from "@/components/layout/app-shell";
import { restoreAuthSession } from "@/features/auth/lib/auth";
import { Button } from "@/components/ui/button";

// 无路径布局：验证登录后加载应用外壳，URL 中不会出现 _app。
export const Route = createFileRoute("/_app")({
  beforeLoad: async ({ location }) => {
    if (!(await restoreAuthSession())) {
      throw redirect({ to: "/sign-in", search: { redirect: location.href } });
    }
  },
  errorComponent: SessionError,
  component: AppShell,
});

function SessionError({ error }: ErrorComponentProps) {
  const router = useRouter();
  return (
    <main className="flex min-h-dvh flex-col items-center justify-center gap-4 px-6 text-center">
      <h1 className="text-lg font-semibold">暂时无法验证登录状态</h1>
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
