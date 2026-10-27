/** 桌面端提供给页面的应用信息。 */
export interface DesktopInfo {
  version: string;
  electron: string;
  platform: string;
}

/** 通过 Preload 暴露的桌面能力。 */
export interface DesktopBridge {
  /** 设备通道建立或重连成功时通知页面。 */
  onDeviceConnected?(listener: () => void): () => void;
  getInfo(): Promise<DesktopInfo>;
  /** 向 Main 同步当前登录，建立用户设备出站连接；退出时传 null。 */
  setSession(token: string | null): Promise<{ deviceId: string | null }>;
  /** 按稳定的 Agent 标识创建工作目录。 */
  ensureAgentWorkspace(agentId: string): Promise<void>;
}
