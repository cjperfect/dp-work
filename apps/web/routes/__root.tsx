import { createRootRoute, Link, Outlet } from "@tanstack/react-router";

export const Route = createRootRoute({
  component: Outlet,
  notFoundComponent: NotFoundPage,
});

function NotFoundPage() {
  return (
    <main className="flex min-h-dvh flex-col items-center justify-center gap-4">
      <h1 className="text-xl font-semibold">页面不存在</h1>
      <Link to="/" className="text-sm underline">
        返回首页
      </Link>
    </main>
  );
}
