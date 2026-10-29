import { app, BrowserWindow, nativeImage, shell } from "electron";
import { readFileSync } from "node:fs";
import path from "node:path";
import { isAppUrl, canCaptureMicrophone } from "./config";
import { DESKTOP_TITLEBAR_HEIGHT } from "@dp-work/protocols/desktop";

/** 创建主窗口并限制导航和媒体权限。 */
export function createMainWindow(url: string, onClosed: () => void): BrowserWindow {
  const origin = new URL(url).origin;
  const icon = nativeImage.createFromBuffer(
    readFileSync(path.join(app.getAppPath(), "resources/icon.png")),
  );
  if (process.platform === "darwin") app.dock?.setIcon(icon);
  const window = new BrowserWindow({
    icon,
    title: "企业 Agent 平台",
    titleBarStyle: "hidden",
    ...(process.platform === "darwin"
      ? { trafficLightPosition: { x: 12, y: 9 } }
      : {
          titleBarOverlay: {
            color: "#f3f3f3",
            symbolColor: "#171717",
            height: DESKTOP_TITLEBAR_HEIGHT,
          },
        }),
    width: 1440,
    height: 940,
    minWidth: 1000,
    minHeight: 680,
    show: false,
    backgroundColor: "#ffffff",
    webPreferences: {
      additionalArguments: [`--dp-titlebar-height=${DESKTOP_TITLEBAR_HEIGHT}`],
      preload: path.join(__dirname, "../preload/index.js"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      partition: "persist:dp-work",
    },
  });
  window.webContents.setWindowOpenHandler(({ url: target }) => {
    if (isAppUrl(target, origin)) {
      void window.loadURL(target);
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
  window.webContents.session.setPermissionRequestHandler(
    (contents, permission, callback, details) => {
      const mediaTypes = "mediaTypes" in details ? details.mediaTypes : undefined;
      callback(
        contents === window.webContents &&
          permission === "media" &&
          details.isMainFrame &&
          canCaptureMicrophone(details.requestingUrl, origin, mediaTypes),
      );
    },
  );
  window.webContents.session.setPermissionCheckHandler(
    (contents, permission, requestingOrigin, details) =>
      contents === window.webContents &&
      permission === "media" &&
      details.isMainFrame &&
      canCaptureMicrophone(requestingOrigin, origin, [details.mediaType ?? "unknown"]),
  );
  window.once("ready-to-show", () => window.show());
  window.on("closed", onClosed);
  return window;
}
