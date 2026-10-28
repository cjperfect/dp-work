import { useEffect, useState } from "react";
import { BookOpen, Bot, Boxes, Package, Plug, Settings2 } from "lucide-react";
import { Link } from "@tanstack/react-router";
import { ChatProjectDirectory } from "./components/chat-project-directory";
import { AgentApprovals } from "./components/agent-approvals";
import { AgentConfigDialog } from "./components/agent-config-dialog";
import { Thread } from "@/components/assistant-ui/elements/thread.aui";
import { Button, buttonVariants } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { useKnowledgeBases } from "@/features/knowledge/hooks/use-knowledge-bases";
import { useSkills } from "@/features/skills/hooks/use-skills";
import { useConnectors } from "@/stores/connectors";
import { useAuthStore } from "@/stores/auth";
import type { AgentId } from "@/interfaces/app";
import type { AgentConfig } from "@/types/agent";
import { ensureAgentChat, saveAgent, useAgentStore } from "@/stores/agent";
import { useAgentCode } from "@/features/agent/hooks/use-agent-code";
export { AGENTS } from "./constants/agents";
export type { AgentMeta } from "./constants/agents";
function AgentWelcome() {
  const code = useAgentCode();
  const agent = useAgentStore((state) => state.agents.find((row) => row.code === code));
  return (
    <div className="max-w-xl px-2">
      <p className="mb-3 text-xs tracking-[.18em] text-muted-foreground">YOUR AGENT WORKSPACE</p>
      <h1 className="text-2xl font-semibold tracking-tight">
        与{agent?.name ?? "Agent"}开始一段会话
      </h1>
      <p className="mt-3 text-sm leading-7 text-muted-foreground">{agent?.description}</p>
    </div>
  );
}
const components = {
  Welcome: AgentWelcome,
  Approvals: AgentApprovals,
  ComposerHeader: ChatProjectDirectory,
};
export function AgentPage({ agentId }: { agentId: AgentId }) {
  const owner = useAuthStore((state) => state.user?.id);
  const state = useAgentStore();
  const agent =
    state.owner === owner ? state.agents.find((row) => row.code === agentId) : undefined;
  const selected = state.selected[agentId];
  const [error, setError] = useState<string | null>(null);
  const [reloading, setReloading] = useState(false);
  const needsChat = selected === null;
  useEffect(() => {
    let alive = true;
    setError(null);
    if (!owner) return;
    void ensureAgentChat(agentId).catch((cause) => {
      if (alive) setError(cause instanceof Error ? cause.message : "无法恢复会话");
    });
    return () => {
      alive = false;
    };
  }, [agentId, owner, needsChat]);
  async function reloadChat() {
    if (!owner || reloading) return;
    setReloading(true);
    setError(null);
    try {
      await ensureAgentChat(agentId, true);
    } catch (cause) {
      if (useAuthStore.getState().user?.id === owner)
        setError(cause instanceof Error ? cause.message : "无法恢复会话，请重试。");
    } finally {
      setReloading(false);
    }
  }
  if (!owner)
    return (
      <div className="grid h-full place-content-center gap-4 p-6 text-center">
        <p className="text-sm text-muted-foreground">请登录后使用 Agent 会话。</p>
        <Link
          to="/sign-in"
          search={{ redirect: agentId === "general" ? "/" : "/product" }}
          className={buttonVariants()}
        >
          前往登录
        </Link>
      </div>
    );
  if (!agent || error || state.error)
    return (
      <div className="grid h-full place-content-center gap-4 p-6 text-center">
        <p
          role={error || state.error ? "alert" : "status"}
          className="text-sm text-muted-foreground"
        >
          {error ?? state.error ?? "正在恢复 Agent 工作空间…"}
        </p>
        {(error || state.error) && (
          <Button disabled={reloading} onClick={() => void reloadChat()}>
            {reloading ? "正在重新加载…" : "重新加载"}
          </Button>
        )}
      </div>
    );
  return (
    <div className="flex h-full w-full">
      <div className="flex min-w-0 flex-1 flex-col">
        <Thread components={components} />
      </div>
      <AgentPanel agent={agent} />
    </div>
  );
}
function AgentPanel({ agent }: { agent: AgentConfig }) {
  const configBusy = useAgentStore((state) => state.configBusy);
  const { bases, loading, error: kbError, reload } = useKnowledgeBases();
  const { connectors } = useConnectors();
  const connected = connectors.filter((connector) => connector.status === "connected");
  const {
    skills,
    error: skillsError,
    loading: skillsLoading,
    reload: reloadSkills,
  } = useSkills(agent.code);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  async function save(changes: Partial<AgentConfig>) {
    setError(null);
    setSaved(false);
    try {
      await saveAgent(agent.code, {
        name: agent.name,
        department: agent.department,
        description: agent.description,
        knowledge_base_ids: agent.knowledge_base_ids,
        skill_ids: agent.skill_ids,
        ...changes,
      });
      setSaved(true);
      return true;
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "配置保存失败");
      return false;
    }
  }
  const Icon = agent.code === "general" ? Bot : Boxes;
  return (
    <aside className="flex w-72 shrink-0 flex-col gap-6 overflow-y-auto border-l bg-background px-4 py-5 md:w-80">
      <section>
        <div className="flex items-start justify-between gap-2">
          <div className="flex items-center gap-2.5">
            <span className="grid size-10 shrink-0 place-items-center rounded-xl bg-muted">
              <Icon className="size-5" />
            </span>
            <div>
              <h2 className="text-sm font-semibold">{agent.name}</h2>
              <p className="mt-1 text-xs text-muted-foreground">{agent.department}</p>
            </div>
          </div>
          <AgentConfigDialog key={agent.code} agent={agent} />
        </div>
        <p className="mt-3 text-xs leading-6 text-muted-foreground">{agent.description}</p>
      </section>
      <section className="grid gap-2">
        <div className="flex items-center justify-between">
          <h3 className="text-xs font-medium text-muted-foreground">关联技能</h3>
          <Link to="/skills" className={buttonVariants({ variant: "ghost", size: "xs" })}>
            <Settings2 className="size-3" />
            配置
          </Link>
        </div>
        <ul className="grid gap-2" aria-label="已关联技能">
          {skills.map((skill) => (
            <li
              key={skill.id}
              className="flex items-center gap-2 rounded-lg border px-3 py-2 text-xs"
            >
              <Package className="size-3.5 shrink-0 text-muted-foreground" aria-hidden="true" />
              <span className="min-w-0 break-words">{skill.name}</span>
            </li>
          ))}
        </ul>
        {skillsError && (
          <button
            type="button"
            className="text-left text-xs text-destructive"
            onClick={() => void reloadSkills()}
          >
            {skillsError}，点击重试
          </button>
        )}
        {skillsLoading && <p className="text-xs text-muted-foreground">正在读取已安装技能…</p>}
        {!skillsLoading && !skillsError && !skills.length && (
          <p className="rounded-lg border border-dashed p-3 text-xs text-muted-foreground">
            暂无关联技能，可前往技能配置安装。
          </p>
        )}
      </section>
      <section className="grid gap-2">
        <div className="flex items-center justify-between">
          <h3 className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
            <Plug className="size-3.5" />
            已连接的连接器
          </h3>
          <Link to="/connectors" className={buttonVariants({ variant: "ghost", size: "xs" })}>
            <Settings2 className="size-3" />
            管理
          </Link>
        </div>
        <ul className="grid gap-2" aria-label="已连接的连接器">
          {connected.map((connector) => (
            <li key={connector.id} className="rounded-lg border px-3 py-2.5">
              <div className="flex items-center justify-between gap-2">
                <span className="text-xs font-medium">{connector.name}</span>
                <span className="flex shrink-0 items-center gap-1 text-[10px] text-emerald-700">
                  <span className="size-1.5 rounded-full bg-emerald-500" />
                  已连接
                </span>
              </div>
              {connector.account && (
                <p
                  className="mt-1.5 truncate text-[11px] text-muted-foreground"
                  title={connector.account}
                >
                  {connector.account}
                </p>
              )}
            </li>
          ))}
        </ul>
        {!connected.length && (
          <p className="rounded-lg border border-dashed p-3 text-xs text-muted-foreground">
            暂无已连接的连接器。
          </p>
        )}
      </section>
      <section className="grid gap-2">
        <h3 className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
          <BookOpen className="size-3.5" />
          默认关联知识库
        </h3>
        <p className="text-[11px] leading-5 text-muted-foreground">
          在这里配置 Agent 关联的知识库。
        </p>
        {loading && <p className="text-xs text-muted-foreground">正在读取知识库…</p>}
        {kbError && (
          <Button variant="outline" size="xs" onClick={reload}>
            知识库读取失败，重试
          </Button>
        )}
        {!loading && !kbError && !bases.length && (
          <Link
            to="/knowledge"
            className="rounded-lg border border-dashed p-3 text-xs text-muted-foreground"
          >
            先创建一个知识库
          </Link>
        )}
        {bases.map((base) => (
          <label
            key={base.id}
            className="flex items-center justify-between gap-2 rounded-lg border px-3 py-2 text-xs"
          >
            <span className="min-w-0 truncate">{base.name}</span>
            <Switch
              checked={agent.knowledge_base_ids.some((id) => String(id) === base.id)}
              disabled={configBusy}
              aria-label={`默认关联 ${base.name}`}
              onCheckedChange={(checked) =>
                void save({
                  knowledge_base_ids: checked
                    ? [...agent.knowledge_base_ids, base.id]
                    : agent.knowledge_base_ids.filter((id) => String(id) !== base.id),
                })
              }
            />
          </label>
        ))}
      </section>
      <div className="mt-auto space-y-2 text-[11px] leading-5 text-muted-foreground">
        {configBusy && <p role="status">正在保存配置…</p>}
        {saved && (
          <p role="status" className="text-emerald-700">
            配置已保存在当前浏览器。
          </p>
        )}
        {error && (
          <p role="alert" className="text-destructive">
            {error}
          </p>
        )}
        <p>
          会话历史已同步到服务器。关联知识库后可检索已向量化的文档；技能按需加载；危险操作需要审批。
        </p>
      </div>
    </aside>
  );
}
