import { app, ipcMain, type BrowserWindow, type IpcMainInvokeEvent } from "electron";
import type { DesktopInfo } from "@dp-work/protocols/desktop";
import type { DeviceBridge } from "./device/bridge";
import { isAppUrl } from "./config";
import { ensureAgentWorkspace } from "./storage/persistence";

interface DesktopIpcContext {
  getWindow(): BrowserWindow | null;
  getOrigin(): string;
  getBridge(): DeviceBridge | null;
  workspace: string;
}

/** 注册桌面 IPC，执行前验证主窗口及主框架来源。 */
export function registerDesktopIpc(context: DesktopIpcContext): void {
  /** 检查桌面 IPC 请求来源。 */
  function assertDesktopSender(event: IpcMainInvokeEvent): void {
    const window = context.getWindow();
    const origin = context.getOrigin();
    if (
      !window ||
      event.sender !== window.webContents ||
      event.senderFrame !== window.webContents.mainFrame ||
      !isAppUrl(event.senderFrame.url, origin)
    )
      throw new Error("无效的桌面请求来源。");
  }

  ipcMain.handle("desktop:session", (event, token: unknown) => {
    assertDesktopSender(event);
    if (token !== null && (typeof token !== "string" || token.length > 8192))
      throw new Error("登录凭证无效。");
    return context.getBridge()?.setSession(token) ?? { deviceId: null };
  });

  ipcMain.handle("desktop:info", (event): DesktopInfo => {
    assertDesktopSender(event);
    return {
      version: app.getVersion(),
      electron: process.versions.electron,
      platform: process.platform,
    };
  });

  ipcMain.handle("desktop:ensure-agent-workspace", (event, agentId: unknown): void => {
    assertDesktopSender(event);
    ensureAgentWorkspace(context.workspace, agentId);
  });
}
