import { app, BrowserWindow, dialog } from "electron";
import path from "node:path";
import { mkdirSync, readFileSync } from "node:fs";
import { desktopPort, developmentUrl, apiBaseUrl } from "./config";
import { startWebServer, waitForWeb } from "./web/server";
import { migrateProfile, persistencePaths } from "./storage/persistence";
import { sidecarOptions } from "./sidecar/config";
import { SidecarManager } from "./sidecar/manager";
import { DeviceBridge, installationId } from "./device/bridge";
import { createMainWindow } from "./window";
import { registerDesktopIpc } from "./ipc";

let window: BrowserWindow | null = null;
let webServer: Awaited<ReturnType<typeof startWebServer>> | null = null;
let quitting = false;
let origin = "";
let sidecar: SidecarManager | null = null;
let bridge: DeviceBridge | null = null;
let cleanupComplete = false;

app.setName("DP Work");
const legacyDataPath = app.getPath("userData");
const storage = persistencePaths(
  app.isPackaged,
  app.getPath("home"),
  path.resolve(__dirname, "../../../.."),
);
for (const directory of [
  storage.data,
  storage.logs,
  storage.cache,
  storage.temp,
  storage.crashes,
  storage.workspace,
])
  mkdirSync(directory, { recursive: true, mode: 0o700 });
app.setPath("userData", storage.data);
app.setPath("sessionData", storage.data);
app.setPath("crashDumps", storage.crashes);
app.setAppLogsPath(storage.logs);
app.commandLine.appendSwitch("disk-cache-dir", storage.cache);

/** 打开主窗口，加载前先提供给 IPC 来源校验。 */
async function createWindow(url: string): Promise<void> {
  window = createMainWindow(url, () => {
    window = null;
  });
  await window.loadURL(url);
}

registerDesktopIpc({
  getWindow: () => window,
  getOrigin: () => origin,
  getBridge: () => bridge,
  workspace: storage.workspace,
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
      const webRoot = app.isPackaged
        ? path.join(process.resourcesPath, "web")
        : path.resolve(__dirname, "../../build/web");
      const publicConfig = bundled
        ? (JSON.parse(readFileSync(path.join(webRoot, "../web-config.json"), "utf8")) as {
            apiBaseUrl: string;
          })
        : null;
      const api = apiBaseUrl(
        process.env.DESKTOP_API_BASE_URL ?? publicConfig?.apiBaseUrl ?? "http://127.0.0.1:8000",
      );
      const managedSidecar = sidecarOptions(
        app.isPackaged,
        path.resolve(__dirname, "../../../.."),
        process.resourcesPath,
        storage.logs,
      );
      if (managedSidecar) {
        const environmentFile =
          process.env.DP_SIDECAR_ENV_FILE ??
          (app.isPackaged
            ? path.join(storage.root, "config/sidecar.env")
            : path.join(managedSidecar.cwd, ".env"));
        managedSidecar.env = {
          ...managedSidecar.env,
          API_INTERNAL_URL: api,
          DP_DATA_DIR: storage.data,
          DP_SIDECAR_ENV_FILE: environmentFile,
        };
        sidecar = new SidecarManager(managedSidecar, (error) => {
          if (!quitting) dialog.showErrorBox("Sidecar 服务异常", error.message);
        });
        await sidecar.start();
        bridge = new DeviceBridge(
          api,
          installationId(path.join(storage.data, "device-id")),
          (job, signal) => sidecar!.request(job, signal),
          () => {
            if (window && !window.isDestroyed())
              window.webContents.send("desktop:device-connected");
          },
        );
      }
      if (quitting) return;
      let url: string;
      if (bundled) {
        const port = desktopPort(process.env.DESKTOP_WEB_PORT);
        const root = app.isPackaged
          ? path.join(process.resourcesPath, "web")
          : path.resolve(__dirname, "../../build/web");
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

app.on("before-quit", (event) => {
  if (cleanupComplete) return;
  event.preventDefault();
  if (quitting) return;
  quitting = true;
  webServer?.close();
  webServer?.closeAllConnections();
  webServer = null;
  bridge?.stop();
  void (sidecar?.stop() ?? Promise.resolve()).finally(() => {
    cleanupComplete = true;
    app.quit();
  });
});
process.once("exit", () => sidecar?.forceStop());
process.once("SIGTERM", () => app.quit());
process.once("SIGINT", () => app.quit());
app.on("window-all-closed", () => {
  if (process.platform !== "darwin") app.quit();
});
