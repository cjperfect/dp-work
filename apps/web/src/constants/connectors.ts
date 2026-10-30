import type { Connector } from "@/interfaces/connectors";
/** 连接器目录：实际授权状态从本机 API 获取。 */

export const CONNECTORS: Connector[] = [
  {
    id: "lark-cli",
    name: "飞书 CLI",
    description:
      "通过飞书官方 CLI 完成应用配置、用户授权和身份验证。授权后 Agent 可搜索、读取和创建飞书文档，创建前需要审批；文档权限不足时请重新授权。",
    status: "disconnected",
    capabilities: ["文档搜索", "读取文档", "审批创建文档"],
  },
];

/** 即将接入的连接器（占位展示） */
export const UPCOMING_CONNECTORS: { name: string; description: string }[] = [
  { name: "企业微信", description: "同步通讯录与消息，Agent 支持企业微信会话问答" },
  { name: "钉钉", description: "待定" },
];
