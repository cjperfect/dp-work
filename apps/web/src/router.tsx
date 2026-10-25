import { PagePending } from "@/components/layout/page-pending";
import { PageError } from "@/components/layout/page-error";
import { useEffect } from "react";
import { safeRedirect } from "@/stores/auth";
import { onUnauthorized } from "@/lib/http";
import { createRouter, RouterProvider } from "@tanstack/react-router";
import { routeTree } from "@/routeTree.gen";

const router = createRouter({
  routeTree,
  defaultPendingComponent: PagePending,
  defaultErrorComponent: PageError,
});

declare module "@tanstack/react-router" {
  interface Register {
    router: typeof router;
  }

  interface StaticDataRouteOption {
    title?: string;
  }
}

export function AppRouter() {
  useEffect(
    () =>
      onUnauthorized(() => {
        const destination = router.state.location.href;
        if (/^\/sign-(in|up)(\/|$|\?)/.test(destination)) return;
        void router.navigate({
          to: "/sign-in",
          search: { redirect: safeRedirect(destination) },
          replace: true,
        });
      }),
    [],
  );
  return <RouterProvider router={router} />;
}
