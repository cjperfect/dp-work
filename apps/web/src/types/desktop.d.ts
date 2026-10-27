import type { DesktopBridge } from "@dp-work/protocols/desktop";

declare global {
  interface Window {
    desktop?: DesktopBridge;
  }
}
