import { createRootRoute } from "@tanstack/react-router";
import { NotFoundPage } from "@/components/layout/not-found-page";
import { RootLayout } from "@/components/layout/root-layout";

export const Route = createRootRoute({ component: RootLayout, notFoundComponent: NotFoundPage });
