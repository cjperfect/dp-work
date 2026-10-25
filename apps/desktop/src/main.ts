import { app, BrowserWindow, dialog, ipcMain, shell, type IpcMainInvokeEvent } from "electron";
import path from "node:path";
import { mkdirSync, readFileSync } from "node:fs";
import type { DesktopInfo } from "@dp-work/contracts";
import { desktopPort, developmentUrl, isAppUrl } from "./config";
import { startWebServer, waitForWeb } from "./server";
import { ensureAgentWorkspace, migrateProfile, persistencePaths } from "./persistence";

let window: BrowserWindow | null = null;
let webServer: Awaited<ReturnType<typeof startWebServer>> | null = null;
let quitting = false;
let origin = "";

app.setName("DP Work");
const legacyDataPath = app.getPath("userData");
const storage = persistencePaths(
  app.isPackaged,
  app.getPath("home"),
  path.resolve(__dirname, "../../.."),
);
for (const directory of [
  storage.data,
  storage.logs,
  storage.cache,
  storage.crashes,
  storage.workspace,
])
  mkdirSync(directory, { recursive: true, mode: 0o700 });
app.setPath("userData", storage.data);
app.setPath("sessionData", storage.data);
app.setPath("crashDumps", storage.crashes);
app.setAppLogsPath(storage.logs);
app.commandLine.appendSwitch("disk-cache-dir", storage.cache);

/** 创建桌面主窗口。 */
async function createWindow(url: string): Promise<void> {
  window = new BrowserWindow({
    title: "企业 Agent 平台",
    width: 1440,
    height: 940,
    minWidth: 1000,
    minHeight: 680,
    show: false,
    backgroundColor: "#ffffff",
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      partition: "persist:dp-work",
    },
  });
  window.webContents.setWindowOpenHandler(({ url: target }) => {
    if (isAppUrl(target, origin)) {
      void window?.loadURL(target);
    } else {
      try {
        const external = new URL(target);
        if (external.protocol === "https:" && !external.username && !external.password)
          void shell.openExternal(target);
      } catch {
        // 忽略无效链接。
      }
    }
    return { action: "deny" };
  });
  window.webContents.on("will-navigate", (event, target) => {
    if (!isAppUrl(target, origin)) event.preventDefault();
  });
  window.webContents.on("will-attach-webview", (event) => event.preventDefault());
  window.webContents.session.setPermissionRequestHandler((_contents, _permission, callback) =>
    callback(false),
  );
  window.webContents.session.setPermissionCheckHandler(() => false);
  window.once("ready-to-show", () => window?.show());
  window.on("closed", () => {
    window = null;
  });
  await window.loadURL(url);
}

/** 检查桌面 IPC 请求来源。 */
function assertDesktopSender(event: IpcMainInvokeEvent): void {
  if (
    !window ||
    event.sender !== window.webContents ||
    event.senderFrame !== window.webContents.mainFrame ||
    !isAppUrl(event.senderFrame.url, origin)
  )
    throw new Error("无效的桌面请求来源。");
}

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
  ensureAgentWorkspace(storage.workspace, agentId);
});

if (!app.requestSingleInstanceLock()) {
  app.quit();
} else {
  try {
    migrateProfile(storage.data, legacyDataPath);
  } catch (cause) {
    dialog.showErrorBox("本地数据初始化失败", String(cause));
    app.exit(1);
  }
  app.on("second-instance", () => {
    if (window?.isMinimized()) window.restore();
    window?.show();
    window?.focus();
  });
  app
    .whenReady()
    .then(async () => {
      const bundled = app.isPackaged || process.env.DESKTOP_BUNDLED_WEB === "1";
      let url: string;
      if (bundled) {
        const port = desktopPort(process.env.DESKTOP_WEB_PORT);
        const root = app.isPackaged
          ? path.join(process.resourcesPath, "web")
          : path.resolve(__dirname, "../build/web");
        const configFile = path.join(root, "../web-config.json");
        const config = JSON.parse(readFileSync(configFile, "utf8")) as { apiBaseUrl: string };
        webServer = await startWebServer(
          root,
          port,
          process.env.DESKTOP_API_BASE_URL ?? config.apiBaseUrl,
        );
        webServer.on("error", (cause) => {
          if (!quitting) {
            dialog.showErrorBox("Web 服务异常", String(cause));
            app.quit();
          }
        });
        url = `http://127.0.0.1:${port}/`;
      } else {
        url = developmentUrl(process.env.DESKTOP_WEB_URL ?? "http://localhost:3000/");
      }
      origin = new URL(url).origin;
      await waitForWeb(url, () => quitting || (bundled && !webServer));
      if (!quitting) await createWindow(url);
      app.on("activate", () => {
        if (!quitting && BrowserWindow.getAllWindows().length === 0)
          void createWindow(url).catch((cause: unknown) =>
            dialog.showErrorBox("窗口打开失败", String(cause)),
          );
      });
    })
    .catch((cause: unknown) => {
      if (!quitting) dialog.showErrorBox("桌面应用启动失败", String(cause));
      app.quit();
    });
}

app.on("before-quit", () => {
  quitting = true;
  webServer?.close();
  webServer?.closeAllConnections();
  webServer = null;
});
app.on("window-all-closed", () => {
  if (process.platform !== "darwin") app.quit();
});
