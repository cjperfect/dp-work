import { contextBridge, ipcRenderer } from "electron";
import type { DesktopBridge } from "@dp-work/contracts";

const desktop: DesktopBridge = {
  getInfo: () => ipcRenderer.invoke("desktop:info"),
  ensureAgentWorkspace: (agentId) => ipcRenderer.invoke("desktop:ensure-agent-workspace", agentId),
};

contextBridge.exposeInMainWorld("desktop", desktop);
