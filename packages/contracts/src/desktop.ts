/** 桌面端提供给页面的应用信息。 */
export interface DesktopInfo {
  version: string;
  electron: string;
  platform: string;
}

/** 通过 Preload 暴露的桌面能力。 */
export interface DesktopBridge {
  getInfo(): Promise<DesktopInfo>;
}
