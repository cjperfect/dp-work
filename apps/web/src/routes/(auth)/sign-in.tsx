import { SignInPage } from "@/features/auth/components/auth-page";
import { createFileRoute } from "@tanstack/react-router";
import { redirectAuthenticatedUser } from "@/features/auth/lib/auth";
import { safeRedirect } from "@/stores/auth";

export const Route = createFileRoute("/(auth)/sign-in")({
  validateSearch: (search: Record<string, unknown>): { redirect?: string } => ({
    redirect: safeRedirect(search.redirect),
  }),
  beforeLoad: ({ search }) => redirectAuthenticatedUser(search.redirect),
  component: SignInPage,
});
