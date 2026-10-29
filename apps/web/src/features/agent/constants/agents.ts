/**
 * Agent 常量（features/agent/constants/agents.ts）
 */
import type { AgentId } from "@/interfaces/app";

export type AgentMeta = {
  id: AgentId;
  numericId: number;
  capabilities: string[];
  name: string;
  department: string;
  description: string;
  skills: string[];
};

// 内置伙伴目录；通用 Agent 默认启用，部门 Agent 由用户主动添加。
export const AGENTS: AgentMeta[] = [
  {
    id: "general",
    numericId: 1,
    capabilities: ["日常问答", "资料整理", "任务执行"],
    name: "通用 Agent",
    department: "全员",
    description: "面向全员的通用问答与任务执行，不绑定特定部门业务范畴",
    skills: [],
  },
  {
    id: "product",
    numericId: 2,
    capabilities: ["需求梳理", "产品方案", "评审准备"],
    name: "产品 Agent",
    department: "产品部",
    description: "面向产品团队，按产品部业务范畴与 SOP 输出需求、评审与版本说明",
    skills: [],
  },
  {
    id: "ui",
    numericId: 3,
    name: "UI Agent",
    department: "设计部",
    description: "面向界面与交互设计，协助梳理页面结构、视觉规范与交互细节，让设计方案更清晰。",
    capabilities: ["界面设计", "交互细节", "设计规范"],
    skills: [],
  },
];

export const AGENT_PATHS = { general: "/", product: "/product", ui: "/ui" } as const;
export function agentPath(code: AgentId) {
  return AGENT_PATHS[code];
}
