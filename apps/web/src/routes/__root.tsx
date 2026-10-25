import { createRootRoute, Outlet } from "@tanstack/react-router";
import { NotFoundPage } from "@/components/layout/not-found-page";

export const Route = createRootRoute({ component: Outlet, notFoundComponent: NotFoundPage });
