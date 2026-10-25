/**
 * 技能常量（features/skills/constants/skills.ts）
 */

export type SkillStatus = "installed" | "available";

export type AgentTarget = "general" | "product" | "all";

export type SkillItem = {
  id: string;
  name: string;
  department: string;
  description: string;
  status: SkillStatus;
  /** 已安装的目标 Agent（具体到 general / product；all 仅作为查看/批量操作的快捷方式，不落库） */
  installedFor: ("general" | "product")[];
};

// 静态示例数据：仅用于搭建页面结构，后续接入真实技能市场 / 安装接口
export const SKILLS: SkillItem[] = [
  {
    id: "s-001",
    name: "SOP 规范化",
    department: "产研中心",
    description: "按部门 SOP 自动规范输出格式与审批口径，保证对外文档符合规范",
    status: "installed",
    installedFor: ["general", "product"],
  },
  {
    id: "s-002",
    name: "会议纪要生成",
    department: "管理后台",
    description: "从会议转写内容提炼决议、待办与风险项，生成结构化会议纪要",
    status: "installed",
    installedFor: ["general", "product"],
  },
  {
    id: "s-003",
    name: "知识库问答",
    department: "全员",
    description: "基于已授权知识库检索上下文，回答问题时自动附带来源引用",
    status: "installed",
    installedFor: ["general", "product"],
  },
  {
    id: "s-004",
    name: "合同审查",
    department: "法务部",
    description: "审查合同风险条款，输出修改建议与风险等级标注",
    status: "available",
    installedFor: [],
  },
  {
    id: "s-005",
    name: "财报分析",
    department: "财务部",
    description: "读取财报数据生成经营分析与异常项归因",
    status: "available",
    installedFor: [],
  },
  {
    id: "s-006",
    name: "招聘初筛",
    department: "人力部",
    description: "按 JD 要求初筛简历，输出候选人匹配度评分与面试建议",
    status: "available",
    installedFor: [],
  },
];

/** 可安装目标 Agent 选项（与左侧导航 AGENT_NAV 对应） */
export const AGENT_OPTIONS: { value: AgentTarget; label: string }[] = [
  { value: "general", label: "通用 Agent" },
  { value: "product", label: "产品 Agent" },
];
