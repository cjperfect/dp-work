/** 桌面自定义标题栏高度。 */
export const DESKTOP_TITLEBAR_HEIGHT = 32;
/** 本机经文件夹选择器确认的项目目录。 */
export interface LocalProject {
  id: string;
  name: string;
  path: string;
  device_id: string;
}

/** 桌面端提供给页面的应用信息。 */
export interface DesktopInfo {
  version: string;
  electron: string;
  platform: string;
}

export interface DesktopUpdateState {
  revision: number;
  status:
    | "disabled"
    | "idle"
    | "checking"
    | "available"
    | "downloading"
    | "downloaded"
    | "installing"
    | "error";
  currentVersion: string;
  availableVersion?: string;
  percent?: number;
  message?: string;
  retry?: "check" | "download" | "install";
}

/** 通过 Preload 暴露的桌面能力。 */
export interface DesktopBridge {
  windowChrome?: { platform: string; titleBarHeight: number };
  writeClipboard?(text: string): Promise<void>;
  localRequest?(request: LocalRequest): Promise<LocalResponseHead>;
  onLocalChunk?(listener: (chunk: LocalResponseChunk) => void): () => void;
  cancelLocalRequest?(id: string): Promise<void>;
  /** 设备通道建立或重连成功时通知页面。 */
  onDeviceConnected?(listener: () => void): () => void;
  selectProjectDirectory?(): Promise<LocalProject | null>;
  getInfo(): Promise<DesktopInfo>;
  getUpdateState?(): Promise<DesktopUpdateState>;
  checkForUpdates?(): Promise<DesktopUpdateState>;
  downloadUpdate?(): Promise<DesktopUpdateState>;
  installUpdate?(): Promise<DesktopUpdateState>;
  onUpdateState?(listener: (state: DesktopUpdateState) => void): () => void;
  /** 向 Main 同步当前登录，建立用户设备出站连接；退出时传 null。 */
  setSession(token: string | null): Promise<{ deviceId: string | null }>;
  /** 按稳定的 Agent 标识创建工作目录。 */
  ensureAgentWorkspace(agentId: string): Promise<void>;
}

/** 本地兼容业务调用；Main 按白名单路径映射，不允许 Renderer 调任意 RPC。 */
export interface LocalRequest {
  id: string;
  token: string;
  path: string;
  method?: string;
  query?: Record<string, unknown>;
  body?: unknown;
}
export interface LocalResponseHead {
  status: number;
  contentType: string;
}
export type LocalResponseChunk = {
  id: string;
  data?: Uint8Array;
  done?: boolean;
  error?: string;
};
