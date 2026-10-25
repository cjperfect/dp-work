/** 连接器 mock 数据：连接飞书 CLI 等外部服务（UI 骨架，授权流程待接入后端） */

export type ConnectorStatus = "connected" | "disconnected";

export interface Connector {
  id: string;
  name: string;
  description: string;
  /** 连接后的账号信息（mock） */
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
      "连接飞书企业账号后，会议纪要、知识库资料可一键同步到飞书文档 / 多维表格，Agent 输出也可直接沉淀到飞书知识空间。",
    status: "connected",
    account: "chen.jiang@breo.com（飞书企业号）",
    capabilities: ["会议纪要同步", "知识库资料同步", "Agent 输出沉淀"],
  },
];

/** 即将接入的连接器（占位展示） */
export const UPCOMING_CONNECTORS: { name: string; description: string }[] = [
  { name: "企业微信", description: "同步通讯录与消息，Agent 支持企业微信会话问答" },
  { name: "钉钉", description: "待定" },
];
