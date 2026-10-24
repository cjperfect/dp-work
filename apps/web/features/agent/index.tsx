"use client";

import { BookOpen, Bot, Boxes, Package, Plug, Settings2 } from "lucide-react";
import { Link } from "@tanstack/react-router";
import { Thread } from "@/components/assistant-ui/elements/thread.aui";
import { KNOWLEDGE_BASES } from "@/features/knowledge/constants/knowledge-data";
import { CONNECTORS } from "@/features/connectors/constants/connectors";
import { buttonVariants } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { useAppStore } from "@/stores/app-store";
import type { AgentId } from "@/interfaces/app";

export { AGENTS } from "@/features/agent/constants/agents";
export type { AgentMeta } from "@/features/agent/constants/agents";
import { AGENTS } from "@/features/agent/constants/agents";
import type { AgentMeta } from "@/features/agent/constants/agents";

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
          <Link
            to="/skills"
            className={buttonVariants({
              variant: "ghost",
              size: "sm",
              className: "text-muted-foreground hover:text-foreground h-6 px-1.5 text-xs",
            })}
          >
            <Settings2 className="size-3.5" />
            管理
          </Link>
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

      <section className="flex flex-col gap-2">
        <div className="flex items-center justify-between">
          <h2 className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
            <Plug className="size-3.5" />
            连接器
          </h2>
          <Link
            to="/connectors"
            className={buttonVariants({
              variant: "ghost",
              size: "sm",
              className: "text-muted-foreground hover:text-foreground h-6 px-1.5 text-xs",
            })}
          >
            <Settings2 className="size-3.5" />
            管理
          </Link>
        </div>
        <ul className="flex flex-col gap-1.5">
          {CONNECTORS.filter((c) => c.status === "connected").map((connector) => (
            <li
              key={connector.id}
              className="flex items-center justify-between gap-2 rounded-lg border bg-card px-3 py-2"
            >
              <span className="flex min-w-0 items-center gap-2 text-sm">
                <Plug className="text-muted-foreground size-3.5 shrink-0" />
                <span className="truncate">{connector.name}</span>
              </span>
              <span className="bg-emerald-500/10 text-emerald-600 shrink-0 rounded-full px-2 py-0.5 text-[10px]">
                已连接
              </span>
            </li>
          ))}
          {CONNECTORS.filter((c) => c.status === "connected").length === 0 && (
            <li className="text-muted-foreground rounded-lg border border-dashed p-3 text-center text-xs">
              暂无已连接连接器
            </li>
          )}
        </ul>
      </section>

      <p className="text-muted-foreground mt-auto text-[10px]">
        * Agent 信息与知识库开关为 UI 骨架，功能待接入
      </p>
    </aside>
  );
}
