import { createFileRoute, lazyRouteComponent } from "@tanstack/react-router";
import { safeRedirect } from "@/features/auth/lib/auth";

export const Route = createFileRoute("/(auth)/sign-up")({
  validateSearch: (search: Record<string, unknown>): { redirect?: string } => ({
    redirect: safeRedirect(search.redirect),
  }),
  component: lazyRouteComponent(() => import("@/features/auth/components/auth-page"), "SignUpPage"),
});
