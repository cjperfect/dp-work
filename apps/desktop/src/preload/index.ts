import { contextBridge, ipcRenderer } from "electron";
import type { DesktopBridge } from "@dp-work/protocols/desktop";

// 沙箱 preload 只可在运行时加载 electron，窗口参数由 Main 传入。
const titleBarHeight = Number(
  process.argv.find((argument) => argument.startsWith("--dp-titlebar-height="))?.split("=")[1],
);

const desktop: DesktopBridge = {
  windowChrome:
    Number.isFinite(titleBarHeight) && titleBarHeight > 0
      ? { platform: process.platform, titleBarHeight }
      : undefined,
  writeClipboard: (text) => ipcRenderer.invoke("desktop:write-clipboard", text),
  localRequest: (request) => ipcRenderer.invoke("desktop:local-request", request),
  cancelLocalRequest: (id) => ipcRenderer.invoke("desktop:local-cancel", id),
  onLocalChunk: (listener) => {
    const handler = (_event: Electron.IpcRendererEvent, chunk: Parameters<typeof listener>[0]) =>
      listener(chunk);
    ipcRenderer.on("desktop:local-chunk", handler);
    return () => ipcRenderer.removeListener("desktop:local-chunk", handler);
  },
  onDeviceConnected: (listener) => {
    const handler = () => listener();
    ipcRenderer.on("desktop:device-connected", handler);
    return () => ipcRenderer.removeListener("desktop:device-connected", handler);
  },
  selectProjectDirectory: () => ipcRenderer.invoke("desktop:select-project-directory"),
  getInfo: () => ipcRenderer.invoke("desktop:info"),
  getUpdateState: () => ipcRenderer.invoke("desktop:updates-state"),
  checkForUpdates: () => ipcRenderer.invoke("desktop:updates-check"),
  downloadUpdate: () => ipcRenderer.invoke("desktop:updates-download"),
  installUpdate: () => ipcRenderer.invoke("desktop:updates-install"),
  onUpdateState: (listener) => {
    const handler = (_event: Electron.IpcRendererEvent, state: Parameters<typeof listener>[0]) =>
      listener(state);
    ipcRenderer.on("desktop:update-state", handler);
    return () => ipcRenderer.removeListener("desktop:update-state", handler);
  },
  setSession: (token) => ipcRenderer.invoke("desktop:session", token),
  ensureAgentWorkspace: (agentId) => ipcRenderer.invoke("desktop:ensure-agent-workspace", agentId),
};

contextBridge.exposeInMainWorld("desktop", desktop);
