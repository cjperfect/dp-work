"use client";

import { BookOpen, Bot, Boxes, Package, Settings2 } from "lucide-react";
import { Thread } from "@/components/assistant-ui/elements/thread.aui";
import { KNOWLEDGE_BASES } from "@/features/knowledge/data/knowledge-data";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { useAppStore } from "@/stores/app-store";
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

export function AgentPage({ agentId }: { agentId: AgentId }) {
  const agent = AGENTS.find((a) => a.id === agentId) ?? AGENTS[0];

  return (
    <div className="flex h-full w-full">
      <div className="min-w-0 flex-1">
        <Thread />
      </div>
      <AgentDetailPanel agent={agent} />
    </div>
  );
}

function AgentDetailPanel({ agent }: { agent: AgentMeta }) {
  const Icon = agent.id === "general" ? Bot : Boxes;
  const enabledKbs = useAppStore((s) => s.enabledKbs);
  const toggleKb = useAppStore((s) => s.toggleKb);
  const setView = useAppStore((s) => s.setView);

  return (
    <aside className="bg-background flex w-72 shrink-0 flex-col gap-5 overflow-y-auto border-l px-4 py-5 md:w-80">
      <div className="flex flex-col gap-2">
        <div className="flex items-center gap-2.5">
          <div className="bg-muted text-muted-foreground flex size-10 items-center justify-center rounded-xl">
            <Icon className="size-5" />
          </div>
          <div className="flex flex-col gap-0.5">
            <div className="flex items-center gap-2">
              <span className="text-sm font-semibold">{agent.name}</span>
              <span className="bg-muted text-muted-foreground rounded-full px-2 py-0.5 text-xs">
                {agent.department}
              </span>
            </div>
          </div>
        </div>
        <p className="text-muted-foreground text-xs leading-relaxed">{agent.description}</p>
      </div>

      <section className="flex flex-col gap-2">
        <div className="flex items-center justify-between">
          <h2 className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
            <Package className="size-3.5" />
            已安装技能
          </h2>
          <Button
            variant="ghost"
            size="sm"
            className="text-muted-foreground hover:text-foreground h-6 px-1.5 text-xs"
            onClick={() => setView("skills")}
          >
            <Settings2 className="size-3.5" />
            管理
          </Button>
        </div>
        <ul className="flex flex-col gap-1.5">
          {agent.skills.map((skill) => (
            <li
              key={skill}
              className="flex items-center justify-between gap-2 rounded-lg border bg-card px-3 py-2"
            >
              <span className="truncate text-sm">{skill}</span>
              <span className="bg-emerald-500/10 text-emerald-600 shrink-0 rounded-full px-2 py-0.5 text-[10px]">
                已安装
              </span>
            </li>
          ))}
          {agent.skills.length === 0 && (
            <li className="text-muted-foreground rounded-lg border border-dashed p-3 text-center text-xs">
              暂无技能，可前往技能安装页面添加
            </li>
          )}
        </ul>
      </section>

      <section className="flex flex-col gap-2">
        <h2 className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
          <BookOpen className="size-3.5" />
          知识库
        </h2>
        <ul className="flex flex-col gap-1.5">
          {KNOWLEDGE_BASES.map((kb) => (
            <li
              key={kb.id}
              className="flex items-center justify-between gap-2 rounded-lg border bg-card px-3 py-2"
            >
              <span className="flex min-w-0 items-center gap-2 text-sm">
                <BookOpen className="text-muted-foreground size-3.5 shrink-0" />
                <span className="truncate">{kb.name}</span>
              </span>
              <Switch
                checked={enabledKbs.includes(kb.id)}
                onCheckedChange={() => toggleKb(kb.id)}
                aria-label={`开启 ${kb.name}`}
              />
            </li>
          ))}
        </ul>
      </section>

      <p className="text-muted-foreground mt-auto text-[10px]">
        * Agent 信息与知识库开关为 UI 骨架，功能待接入
      </p>
    </aside>
  );
}
