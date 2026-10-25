/** 连接器目录：实际授权状态从本机 API 获取。 */

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

export const CONNECTORS: Connector[] = [
  {
    id: "lark-cli",
    name: "飞书 CLI",
    description:
      "通过飞书官方 CLI 完成应用配置、用户授权和身份验证。业务同步与 Agent 调用后续接入。",
    status: "disconnected",
    capabilities: ["网页授权", "登录验证", "本机凭证管理"],
  },
];

/** 即将接入的连接器（占位展示） */
export const UPCOMING_CONNECTORS: { name: string; description: string }[] = [
  { name: "企业微信", description: "同步通讯录与消息，Agent 支持企业微信会话问答" },
  { name: "钉钉", description: "待定" },
];
