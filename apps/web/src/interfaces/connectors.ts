export type FeishuAuthorization = {
  action: "configure" | "login";
  state: "starting" | "waiting" | "completed" | "failed" | "cancelled";
  url: string | null;
  qr_code: string | null;
  message: string | null;
  expires_at: string;
};

export type FeishuStatus = {
  installed: boolean;
  configured: boolean;
  connected: boolean;
  verified: boolean;
  account: string | null;
  last_verified_at: string | null;
  flow: FeishuAuthorization | null;
};

export type ConnectorStatus = "connected" | "disconnected";

export interface Connector {
  id: string;
  name: string;
  description: string;
  /** 连接后的账号名称 */
  account?: string;
  status: ConnectorStatus;
  /** 连接器能力标签 */
  capabilities: string[];
}
