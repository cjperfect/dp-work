import { AccessSync } from "@/features/access/components/access-sync";
import { DesktopSession } from "./desktop-session";
import { DesktopUpdates } from "@/features/desktop/components/desktop-updates";
import { DesktopTitlebar } from "@/features/desktop/components/desktop-titlebar";
import { PermissionOutlet } from "@/features/access/components/permission-outlet";
import { Toaster } from "@/components/ui/sonner";
import { GenerationNotifications } from "@/features/meetings/components/generation-notifications";

import { ParseNotifications } from "@/features/knowledge/components/parse-notifications";

export function RootLayout() {
  return (
    <>
      <AccessSync />
      <DesktopSession />
      <DesktopTitlebar />
      <DesktopUpdates />
      <PermissionOutlet />
      <GenerationNotifications />
      <ParseNotifications />
      <Toaster />
    </>
  );
}
