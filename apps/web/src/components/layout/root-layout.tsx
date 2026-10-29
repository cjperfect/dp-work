import { DesktopSession } from "./desktop-session";
import { DesktopUpdates } from "@/features/desktop/components/desktop-updates";
import { DesktopTitlebar } from "@/features/desktop/components/desktop-titlebar";
import { Outlet } from "@tanstack/react-router";
import { Toaster } from "@/components/ui/sonner";
import { GenerationNotifications } from "@/features/meetings/components/generation-notifications";

import { ParseNotifications } from "@/features/knowledge/components/parse-notifications";

export function RootLayout() {
  return (
    <>
      <DesktopSession />
      <DesktopTitlebar />
      <DesktopUpdates />
      <Outlet />
      <GenerationNotifications />
      <ParseNotifications />
      <Toaster />
    </>
  );
}
