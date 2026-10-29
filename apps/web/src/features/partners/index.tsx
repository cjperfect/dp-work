import { useState } from "react";
import { Link } from "@tanstack/react-router";
import { ArrowUpRight, Bot, Boxes, Check, Palette, Plus, UsersRound } from "lucide-react";
import { toast } from "sonner";
import { Button, buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { AGENTS, agentPath } from "@/features/agent/constants/agents";
import { addPartner, removePartner, loadAgents, useAgentStore } from "@/stores/agent";
import { useAuthStore } from "@/stores/auth";
import type { AgentId } from "@/interfaces/app";

export function PartnersPage() {
  const owner = useAuthStore((state) => state.user?.id);
  const codes = useAgentStore((state) => state.partnerCodes);
  const storedOwner = useAgentStore((state) => state.owner);
  const loading = useAgentStore((state) => state.loading);
  const error = useAgentStore((state) => state.error);
  const [adding, setAdding] = useState<AgentId | null>(null);
  async function add(code: AgentId, name: string) {
    setAdding(code);
    try {
      await addPartner(code);
      toast.success(`已添加${name}`);
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : "添加失败，请重试。");
    } finally {
      setAdding(null);
    }
  }
  async function remove(code: AgentId, name: string) {
    setAdding(code);
    try {
      await removePartner(code);
      toast.success(`已取消添加${name}`);
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : "取消失败，请重试。");
    } finally {
      setAdding(null);
    }
  }
  return (
    <main className="h-full overflow-y-auto">
      <div className="mx-auto max-w-6xl space-y-9 px-6 py-9 md:px-10 md:py-10">
        <header className="space-y-3">
          <div className="mb-5 inline-flex items-center gap-2 rounded-full border bg-muted/40 px-3 py-1 text-xs text-muted-foreground">
            <UsersRound className="size-3.5" /> 你的协作团队
          </div>
          <h1 className="text-3xl font-semibold tracking-tight">伙伴</h1>
          <p className="max-w-xl text-sm leading-7 text-muted-foreground">
            为工作找到合适的伙伴。添加部门 Agent，它就会出现在左侧「我的 Agent」中。
          </p>
        </header>

        <section
          aria-label="默认伙伴"
          className="flex flex-wrap items-center gap-4 rounded-xl border bg-muted/25 px-5 py-4"
        >
          <div className="grid size-10 shrink-0 place-items-center rounded-xl border bg-background">
            <Bot className="size-5" />
          </div>
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2 text-sm font-medium">
              通用 Agent <span className="text-xs font-normal text-muted-foreground">默认伙伴</span>
            </div>
            <p className="mt-1 text-xs leading-5 text-muted-foreground">
              每个账号都有一位通用伙伴，随时帮你问答、整理资料与执行任务。
            </p>
          </div>
          <Link to="/" className={buttonVariants({ variant: "outline", size: "sm" })}>
            开始对话 <ArrowUpRight className="size-3.5" />
          </Link>
        </section>

        <section aria-labelledby="department-partners" className="space-y-4">
          <div className="flex items-end justify-between gap-4">
            <h2 id="department-partners" className="text-base font-semibold">
              部门伙伴
            </h2>
            <span className="text-xs text-muted-foreground">按需添加，专注各自领域</span>
          </div>
          {error && (
            <div
              role="alert"
              className="flex items-center justify-between rounded-lg border p-4 text-sm"
            >
              <span>{error}</span>
              <Button
                variant="outline"
                size="sm"
                onClick={() => void loadAgents(true).catch(() => {})}
              >
                重新加载
              </Button>
            </div>
          )}
          <div className="grid gap-5 md:grid-cols-2">
            {AGENTS.filter((agent) => agent.id !== "general").map((agent) => {
              const added = !!owner && storedOwner === owner && codes.includes(agent.id);
              const Icon = agent.id === "ui" ? Palette : Boxes;
              return (
                <Card
                  key={agent.id}
                  className="gap-5 shadow-none transition-colors hover:border-foreground/25"
                >
                  <CardHeader className="flex flex-row items-start justify-between gap-4">
                    <div className="flex items-center gap-3">
                      <div
                        className={`grid size-12 place-items-center rounded-2xl ${agent.id === "ui" ? "bg-sky-50 text-sky-700 dark:bg-sky-950/40 dark:text-sky-300" : "bg-amber-50 text-amber-800 dark:bg-amber-950/40 dark:text-amber-300"}`}
                      >
                        <Icon className="size-5" />
                      </div>
                      <div>
                        <CardTitle className="text-base">{agent.name}</CardTitle>
                        <p className="mt-1.5 text-xs text-muted-foreground">{agent.department}</p>
                      </div>
                    </div>
                    {added && (
                      <span className="flex items-center gap-1 text-xs text-emerald-700 dark:text-emerald-400">
                        <Check className="size-3.5" />
                        已添加
                      </span>
                    )}
                  </CardHeader>
                  <CardContent className="flex-1 space-y-5">
                    <p className="min-h-12 text-sm leading-6 text-muted-foreground">
                      {agent.description}
                    </p>
                    <div className="flex flex-wrap gap-2">
                      {agent.capabilities.map((label) => (
                        <span
                          key={label}
                          className="rounded-md bg-muted px-2 py-1 text-xs text-muted-foreground"
                        >
                          {label}
                        </span>
                      ))}
                    </div>
                  </CardContent>
                  <CardFooter className="justify-between gap-3 border-t pt-5">
                    <span className="text-xs text-muted-foreground">独立会话与工作空间</span>
                    {added ? (
                      <div className="flex items-center gap-2">
                        <Button
                          variant="ghost"
                          size="sm"
                          disabled={loading || !!adding}
                          onClick={() => void remove(agent.id, agent.name)}
                        >
                          {adding === agent.id ? "正在取消…" : "取消添加"}
                        </Button>
                        <Link
                          to={agentPath(agent.id)}
                          className={buttonVariants({ variant: "outline", size: "sm" })}
                        >
                          开始对话
                          <ArrowUpRight className="size-3.5" />
                        </Link>
                      </div>
                    ) : (
                      <Button
                        size="sm"
                        disabled={!owner || loading || !!adding}
                        onClick={() => void add(agent.id, agent.name)}
                      >
                        <Plus className="size-3.5" />
                        {adding === agent.id ? "正在添加…" : "添加伙伴"}
                      </Button>
                    )}
                  </CardFooter>
                </Card>
              );
            })}
          </div>
          {!owner && <p className="text-sm text-muted-foreground">登录后可以添加部门伙伴。</p>}
        </section>
      </div>
    </main>
  );
}
