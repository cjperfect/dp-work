import {
  app,
  clipboard,
  dialog,
  ipcMain,
  type BrowserWindow,
  type IpcMainInvokeEvent,
} from "electron";
import type { DesktopInfo, LocalRequest } from "@dp-work/protocols/desktop";
import type { DeviceBridge } from "./device/bridge";
import { isAppUrl } from "./config";
import { registerProject } from "./storage/projects";
import type { LocalGateway } from "./local/gateway";
import { ensureAgentWorkspace } from "./storage/persistence";
import type { UpdateManager } from "./updates/manager";

interface DesktopIpcContext {
  getWindow(): BrowserWindow | null;
  getOrigin(): string;
  getBridge(): DeviceBridge | null;
  getLocalGateway(): LocalGateway | null;
  getUpdates(): UpdateManager | null;
  onSignOut(): void;
  workspace: string;
  data: string;
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

  ipcMain.handle("desktop:write-clipboard", (event, text: unknown) => {
    assertDesktopSender(event);
    if (typeof text !== "string" || text.length > 2_000_000)
      throw new Error("复制内容无效或过长。");
    clipboard.writeText(text);
  });

  ipcMain.handle("desktop:session", (event, token: unknown) => {
    assertDesktopSender(event);
    if (token !== null && (typeof token !== "string" || token.length > 8192))
      throw new Error("登录凭证无效。");
    if (token === null) {
      context.getLocalGateway()?.cancelAll();
      context.onSignOut();
    }
    return context.getBridge()?.setSession(token, false) ?? { deviceId: null };
  });

  ipcMain.handle("desktop:local-request", (event, input: LocalRequest) => {
    assertDesktopSender(event);
    const gateway = context.getLocalGateway();
    if (!gateway) throw new Error("本机 Sidecar 未连接。");
    return gateway.open(input);
  });
  ipcMain.handle("desktop:local-cancel", (event, id: unknown) => {
    assertDesktopSender(event);
    if (typeof id !== "string") throw new Error("请求 ID 无效。");
    context.getLocalGateway()?.cancel(id);
  });

  ipcMain.handle("desktop:select-project-directory", async (event) => {
    assertDesktopSender(event);
    const identity = context.getBridge()?.getIdentity();
    const window = context.getWindow();
    if (!identity || !window) throw new Error("请先登录后添加项目。");
    const result = await dialog.showOpenDialog(window, {
      title: "选择项目工作目录",
      properties: ["openDirectory", "createDirectory"],
    });
    if (result.canceled || !result.filePaths[0]) return null;
    const current = context.getBridge()?.getIdentity();
    if (current?.owner !== identity.owner || current.deviceId !== identity.deviceId)
      throw new Error("登录状态已改变，请重新选择目录。");
    return registerProject(context.data, result.filePaths[0], identity.owner, identity.deviceId);
  });

  ipcMain.handle("desktop:info", (event): DesktopInfo => {
    assertDesktopSender(event);
    return {
      version: app.getVersion(),
      electron: process.versions.electron,
      platform: process.platform,
    };
  });

  for (const [channel, action] of Object.entries({
    "desktop:updates-state": "getState",
    "desktop:updates-check": "check",
    "desktop:updates-download": "download",
    "desktop:updates-install": "install",
  } as const)) {
    ipcMain.handle(channel, (event) => {
      assertDesktopSender(event);
      const updates = context.getUpdates();
      if (!updates) throw new Error("更新服务尚未就绪，请稍后重试。");
      return updates[action]();
    });
  }

  ipcMain.handle("desktop:ensure-agent-workspace", (event, agentId: unknown): void => {
    assertDesktopSender(event);
    ensureAgentWorkspace(context.workspace, agentId);
  });
}
