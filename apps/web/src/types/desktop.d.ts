import type { DesktopBridge } from "@dp-work/contracts";

declare global {
  interface Window {
    desktop?: DesktopBridge;
  }
}
