import { useState } from "react";
import { Loader2, Package, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useAuthStore } from "@/stores/auth";
import { loadAgents, saveAgent, useAgentStore } from "@/stores/agent";
import { useAgentCode } from "@/features/agent/hooks/use-agent-code";
import type { AgentId } from "@/interfaces/app";
import { useAppStore } from "@/stores/app";
export function SkillsPage() {
  const initial = useAgentCode();
  const [code, setCode] = useState<AgentId>(initial);
  const setAgentId = useAppStore((state) => state.setAgentId);
  const [error, setError] = useState<string | null>(null);
  const [installing, setInstalling] = useState<string | null>(null);
  const owner = useAuthStore((state) => state.user?.id);
  const state = useAgentStore();
  const agent = state.owner === owner ? state.agents.find((row) => row.code === code) : undefined;
  async function setInstalled(id: string, installed: boolean) {
    if (!agent || installing) return;
    setInstalling(id);
    setError(null);
    try {
      await saveAgent(code, {
        name: agent.name,
        department: agent.department,
        description: agent.description,
        knowledge_base_ids: agent.knowledge_base_ids,
        skill_ids: installed
          ? [...new Set([...agent.skill_ids, id])]
          : agent.skill_ids.filter((value) => value !== id),
      });
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "配置保存失败");
    } finally {
      setInstalling(null);
    }
  }
  const installed = agent ? state.skills.filter((skill) => agent.skill_ids.includes(skill.id)) : [];
  const available = agent
    ? state.skills.filter((skill) => !agent.skill_ids.includes(skill.id))
    : [];
  function renderCard(skill: (typeof state.skills)[number]) {
    if (!agent) return null;
    const checked = agent.skill_ids.includes(skill.id);
    return (
      <article key={skill.id} className="flex flex-col gap-4 rounded-xl border bg-card p-5">
        <div className="flex items-center gap-3">
          <span className="grid size-9 place-items-center rounded-lg bg-muted">
            <Package className="size-4" />
          </span>
          <div className="min-w-0 flex-1">
            <h2 className="text-sm font-medium">{skill.name}</h2>
            <p className="mt-1 text-xs text-muted-foreground">{skill.department}</p>
          </div>
          {checked ? (
            <Button
              variant="destructive"
              size="sm"
              disabled={installing !== null || state.configBusy}
              aria-label={`卸载技能 ${skill.name}`}
              onClick={() => void setInstalled(skill.id, false)}
            >
              {installing === skill.id ? (
                <Loader2 className="size-4 animate-spin" />
              ) : (
                <Trash2 className="size-4" />
              )}
              {installing === skill.id ? "卸载中…" : "卸载"}
            </Button>
          ) : (
            <Button
              size="sm"
              disabled={installing === skill.id || state.configBusy}
              aria-label={`安装技能 ${skill.name}`}
              onClick={() => void setInstalled(skill.id, true)}
            >
              {installing === skill.id && <Loader2 className="size-4 animate-spin" />}
              {installing === skill.id ? "安装中…" : "安装"}
            </Button>
          )}
        </div>
        <p className="text-xs leading-6 text-muted-foreground">{skill.description}</p>
        <p className="mt-auto text-[11px] text-muted-foreground">
          {checked ? `已安装到 ${agent.name}` : "未安装"}
        </p>
      </article>
    );
  }
  return (
    <div className="h-full overflow-y-auto px-6 py-8 md:px-10">
      <header>
        <p className="mb-2 text-xs tracking-[.18em] text-muted-foreground">AGENT CAPABILITIES</p>
        <h1 className="text-2xl font-semibold">技能配置</h1>
        <p className="mt-2 text-sm text-muted-foreground">
          为不同 Agent 安装或卸载业务技能，配置会保存在当前浏览器。
        </p>
      </header>
      <div className="mt-7 flex items-center gap-3 text-sm">
        配置目标
        <Select
          value={code}
          onValueChange={(value) => {
            if (!value) return;
            setCode(value as AgentId);
            setAgentId(value as AgentId);
          }}
        >
          <SelectTrigger className="w-52" aria-label="技能配置目标">
            <SelectValue>
              {(value) => state.agents.find((row) => row.code === value)?.name ?? ""}
            </SelectValue>
          </SelectTrigger>
          <SelectContent>
            {state.agents.map((row) => (
              <SelectItem key={row.code} value={row.code}>
                {row.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      {(state.error || error) && (
        <div className="mt-4 flex items-center gap-3 text-sm text-destructive" role="alert">
          {error ?? state.error}
          <Button variant="outline" size="sm" onClick={() => void loadAgents(true).catch(() => {})}>
            重新加载
          </Button>
        </div>
      )}
      {!agent && <p className="mt-8 text-sm text-muted-foreground">正在读取 Agent 配置…</p>}
      {agent && (
        <Tabs defaultValue="installed" className="mt-6">
          <TabsList>
            <TabsTrigger value="installed">
              已安装
              {installed.length > 0 && (
                <span className="ml-1 rounded-full bg-background px-1.5 text-xs tabular-nums">
                  {installed.length}
                </span>
              )}
            </TabsTrigger>
            <TabsTrigger value="available">
              未安装
              {available.length > 0 && (
                <span className="ml-1 rounded-full bg-background px-1.5 text-xs tabular-nums">
                  {available.length}
                </span>
              )}
            </TabsTrigger>
          </TabsList>
          <TabsContent value="installed" className="mt-4">
            {installed.length === 0 ? (
              <p className="py-8 text-center text-sm text-muted-foreground">
                还没有安装技能，切换到“未安装”选择添加
              </p>
            ) : (
              <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
                {installed.map(renderCard)}
              </div>
            )}
          </TabsContent>
          <TabsContent value="available" className="mt-4">
            {available.length === 0 ? (
              <p className="py-8 text-center text-sm text-muted-foreground">所有技能都已安装</p>
            ) : (
              <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
                {available.map(renderCard)}
              </div>
            )}
          </TabsContent>
        </Tabs>
      )}
      <p className="mt-6 text-xs text-muted-foreground">
        当前保存技能关联配置；技能执行及审批后续接入。
      </p>
    </div>
  );
}
