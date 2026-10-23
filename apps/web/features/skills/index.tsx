"use client";

import { useState } from "react";
import { CheckCircle2, Download, Package, XCircle } from "lucide-react";
import { Button } from "@/components/ui/button";

type SkillStatus = "installed" | "available";

type SkillItem = {
  id: string;
  name: string;
  department: string;
  description: string;
  status: SkillStatus;
};

// 静态示例数据：仅用于搭建页面结构，后续接入真实技能市场 / 安装接口
const SKILLS: SkillItem[] = [
  {
    id: "s-001",
    name: "SOP 规范化",
    department: "产研中心",
    description: "按部门 SOP 自动规范输出格式与审批口径，保证对外文档符合规范",
    status: "installed",
  },
  {
    id: "s-002",
    name: "会议纪要生成",
    department: "管理后台",
    description: "从会议转写内容提炼决议、待办与风险项，生成结构化会议纪要",
    status: "installed",
  },
  {
    id: "s-003",
    name: "知识库问答",
    department: "全员",
    description: "基于已授权知识库检索上下文，回答问题时自动附带来源引用",
    status: "installed",
  },
  {
    id: "s-004",
    name: "合同审查",
    department: "法务部",
    description: "审查合同风险条款，输出修改建议与风险等级标注",
    status: "available",
  },
  {
    id: "s-005",
    name: "财报分析",
    department: "财务部",
    description: "读取财报数据生成经营分析与异常项归因",
    status: "available",
  },
  {
    id: "s-006",
    name: "招聘初筛",
    department: "人力部",
    description: "按 JD 要求初筛简历，输出候选人匹配度评分与面试建议",
    status: "available",
  },
];

export function SkillsPage() {
  const [tab, setTab] = useState<"installed" | "available">("installed");

  const installed = SKILLS.filter((s) => s.status === "installed");
  const available = SKILLS.filter((s) => s.status === "available");
  const visible = tab === "installed" ? installed : available;

  return (
    <div className="flex w-full flex-1 flex-col gap-6 px-6 py-8 md:px-10">
      <header className="flex flex-col gap-1">
        <h1 className="text-2xl font-semibold tracking-tight">技能安装</h1>
        <p className="text-muted-foreground text-sm">
          每个部门一个 Agent，技能由部门业务范畴与 SOP 自动整理生成，安装后输出内容自动符合部门规范
        </p>
      </header>

      <div className="flex items-center gap-1 border-b">
        <button
          type="button"
          onClick={() => setTab("installed")}
          className={`flex items-center gap-1.5 rounded-t-lg border-b-2 px-3 py-2 text-sm transition-colors ${
            tab === "installed"
              ? "border-primary text-foreground font-medium"
              : "border-transparent text-muted-foreground hover:text-foreground"
          }`}
        >
          <CheckCircle2 className="size-4" />
          已安装
          <span className="text-muted-foreground/60 text-xs">{installed.length}</span>
        </button>
        <button
          type="button"
          onClick={() => setTab("available")}
          className={`flex items-center gap-1.5 rounded-t-lg border-b-2 px-3 py-2 text-sm transition-colors ${
            tab === "available"
              ? "border-primary text-foreground font-medium"
              : "border-transparent text-muted-foreground hover:text-foreground"
          }`}
        >
          <Package className="size-4" />
          未安装
          <span className="text-muted-foreground/60 text-xs">{available.length}</span>
        </button>
      </div>

      <ul className="flex flex-col gap-3">
        {visible.map((skill) => (
          <li
            key={skill.id}
            className="flex items-start justify-between gap-4 rounded-xl border bg-card px-4 py-3.5"
          >
            <div className="flex min-w-0 flex-col gap-1">
              <div className="flex items-center gap-2">
                <span className="text-sm font-medium">{skill.name}</span>
                <span className="bg-muted text-muted-foreground rounded-full px-2 py-0.5 text-xs">
                  {skill.department}
                </span>
              </div>
              <p className="text-muted-foreground text-sm">{skill.description}</p>
            </div>
            {skill.status === "installed" ? (
              <div className="flex shrink-0 items-center gap-2">
                <span className="bg-emerald-500/10 text-emerald-600 flex items-center gap-1 rounded-full px-2 py-0.5 text-xs">
                  <CheckCircle2 className="size-3" />
                  已安装
                </span>
                <Button variant="outline" size="sm" disabled>
                  卸载
                </Button>
              </div>
            ) : (
              <div className="flex shrink-0 items-center gap-2">
                <span className="bg-muted text-muted-foreground flex items-center gap-1 rounded-full px-2 py-0.5 text-xs">
                  <XCircle className="size-3" />
                  未安装
                </span>
                <Button size="sm">
                  <Download className="size-3.5" />
                  安装
                </Button>
              </div>
            )}
          </li>
        ))}
        {visible.length === 0 && (
          <li className="text-muted-foreground rounded-xl border border-dashed p-6 text-center text-sm">
            暂无{tab === "installed" ? "已安装" : "可安装"}技能
          </li>
        )}
      </ul>

      <p className="text-muted-foreground text-xs">* 技能列表与安装 / 卸载为 UI 骨架，功能待接入</p>
    </div>
  );
}
