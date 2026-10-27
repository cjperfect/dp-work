import { contextBridge, ipcRenderer } from "electron";
import type { DesktopBridge } from "@dp-work/protocols/desktop";

const desktop: DesktopBridge = {
  getInfo: () => ipcRenderer.invoke("desktop:info"),
  setSession: (token) => ipcRenderer.invoke("desktop:session", token),
  ensureAgentWorkspace: (agentId) => ipcRenderer.invoke("desktop:ensure-agent-workspace", agentId),
};

contextBridge.exposeInMainWorld("desktop", desktop);
