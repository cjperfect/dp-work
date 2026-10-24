/**
 * Agent 常量（features/agent/constants/agents.ts）
 */
import type { AgentId } from "@/interfaces/app";

export type AgentMeta = {
  id: AgentId;
  name: string;
  department: string;
  description: string;
  skills: string[];
};

// 静态示例数据：Agent 列表实际由当前用户所属部门动态生成（UI 骨架，待接入）
export const AGENTS: AgentMeta[] = [
  {
    id: "general",
    name: "通用 Agent",
    department: "全员",
    description: "面向全员的通用问答与任务执行，不绑定特定部门业务范畴",
    skills: ["知识库问答", "SOP 规范化"],
  },
  {
    id: "product",
    name: "产品 Agent",
    department: "产品部",
    description: "面向产品团队，按产品部业务范畴与 SOP 输出需求、评审与版本说明",
    skills: ["会议纪要生成", "SOP 规范化"],
  },
];
