import { contextBridge, ipcRenderer } from "electron";
import type { DesktopBridge } from "@dp-work/protocols/desktop";

const desktop: DesktopBridge = {
  onDeviceConnected: (listener) => {
    const handler = () => listener();
    ipcRenderer.on("desktop:device-connected", handler);
    return () => ipcRenderer.removeListener("desktop:device-connected", handler);
  },
  selectProjectDirectory: () => ipcRenderer.invoke("desktop:select-project-directory"),
  getInfo: () => ipcRenderer.invoke("desktop:info"),
  setSession: (token) => ipcRenderer.invoke("desktop:session", token),
  ensureAgentWorkspace: (agentId) => ipcRenderer.invoke("desktop:ensure-agent-workspace", agentId),
};

contextBridge.exposeInMainWorld("desktop", desktop);
