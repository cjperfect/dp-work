import { DesktopSession } from "./desktop-session";
import { Outlet } from "@tanstack/react-router";
import { Toaster } from "@/components/ui/sonner";
import { GenerationNotifications } from "@/features/meetings/components/generation-notifications";

import { ParseNotifications } from "@/features/knowledge/components/parse-notifications";

export function RootLayout() {
  return (
    <>
      <DesktopSession />
      <Outlet />
      <GenerationNotifications />
      <ParseNotifications />
      <Toaster />
    </>
  );
}
