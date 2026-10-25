import type { AgentId, ViewKey } from "@/interfaces/app";

export const VIEW_TITLES: Record<ViewKey, string> = {
  chat: "会话",
  meetings: "开始会议",
  skills: "技能安装",
  knowledge: "知识库",
  agent: "Agent",
};

/** 各 Agent 的打招呼语，展示在聊天首屏（UI 骨架，待接入） */
export const AGENT_WELCOME: Record<AgentId, string> = {
  general: "你好，我是通用 Agent。",
  product: "你好，我是产品 Agent。",
};
