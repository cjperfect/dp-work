import { BrowserWindow, shell } from "electron";
import path from "node:path";
import { isAppUrl, canCaptureMicrophone } from "./config";

/** 创建主窗口并限制导航和媒体权限。 */
export function createMainWindow(url: string, onClosed: () => void): BrowserWindow {
  const origin = new URL(url).origin;
  const window = new BrowserWindow({
    title: "企业 Agent 平台",
    width: 1440,
    height: 940,
    minWidth: 1000,
    minHeight: 680,
    show: false,
    backgroundColor: "#ffffff",
    webPreferences: {
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
