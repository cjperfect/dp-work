import { contextBridge, ipcRenderer } from "electron";
import type { DesktopBridge } from "@dp-work/contracts";

const desktop: DesktopBridge = {
  getInfo: () => ipcRenderer.invoke("desktop:info"),
};

contextBridge.exposeInMainWorld("desktop", desktop);
