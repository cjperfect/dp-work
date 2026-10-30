import type { AgentId } from "@/interfaces/app";
import type { AgentConfig, Skill } from "@/interfaces/agent";
import { getAgentConfig } from "@/apis/agents";
import { listConversations, importConversation } from "@/apis/conversations";
import { useAuthStore } from "@/stores/auth";
import { readAccountCache, writeAccountCache } from "@/lib/account-storage";

import { AGENTS } from "@/constants/agents";
import {
  bootstrapRef,
  currentOwner,
  generationRef,
  message,
  owned,
  resetAgents,
  useAgentStore,
  type State,
} from "./state";

export function loadAgents(force = false) {
  const owner = useAuthStore.getState().user?.id;
  if (!owner) return Promise.resolve();
  const old = useAgentStore.getState();
  if (old.owner !== owner) {
    resetAgents();
    useAgentStore.setState({ owner });
  }
  if (bootstrapRef.current) return bootstrapRef.current;
  if (!force && useAgentStore.getState().agents.length && !useAgentStore.getState().error)
    return Promise.resolve();
  const version = generationRef.current;
  useAgentStore.setState({ loading: true, error: null });
  const operation = (async () => {
    try {
      const legacy = readAccountCache<State & { partner_codes?: AgentId[] }>(`agents:${owner}`);
      const saved =
        readAccountCache<
          Pick<State, "agents" | "skills" | "selected"> & { partner_codes?: AgentId[] }
        >(`agent-config:${owner}`) ?? legacy;
      // 内置目录只提供模板；部门伙伴需要当前用户主动添加。
      const seen = new Set<string>();
      const skills: Skill[] = [];
      for (const meta of AGENTS)
        for (const name of meta.skills)
          if (!seen.has(name)) {
            seen.add(name);
            skills.push({ id: name, name, department: meta.department, description: name });
          }
      const agents: AgentConfig[] = AGENTS.map((meta) => ({
        id: meta.numericId,
        owner_id: owner,
        code: meta.id,
        name: meta.name,
        department: meta.department,
        description: meta.description,
        knowledge_base_ids: [],
        skill_ids: meta.skills,
        revision: 1,
        active_thread_id: null,
      }));
      if (!owned(owner) || version !== generationRef.current) return;
      useAgentStore.setState({
        agents: agents.map((agent) => {
          const previous = saved?.agents?.find((row) => row.code === agent.code);
          return previous ? { ...agent, ...previous, id: agent.id, owner_id: owner } : agent;
        }),
        partnerCodes: (saved?.partner_codes ?? []).filter(
          (code) => code !== "general" && AGENTS.some((agent) => agent.id === code),
        ),
        skills: saved?.skills?.length ? saved.skills : skills,
        selected: saved?.selected ?? {},
      });
      if (legacy?.owner === owner) {
        for (const entry of Object.values(legacy.details ?? {})) {
          if (!owned(owner) || version !== generationRef.current) return;
          await importConversation({
            ...entry,
            thread: {
              ...entry.thread,
              title_source:
                entry.thread.title_source ??
                (entry.thread.title === "新会话" ? "pending" : "manual"),
            },
          });
        }
        if (!owned(owner) || version !== generationRef.current) return;
        localStorage.removeItem?.(`dp-work:mock:v1:agents:${owner}`);
      }
      const rows = await listConversations();
      if (!owned(owner) || version !== generationRef.current) return;
      useAgentStore.setState((state) => ({
        loading: false,
        // 保留升级前已有部门会话的可用性，空白的旧默认配置不算添加。
        partnerCodes: [
          ...new Set([
            ...state.partnerCodes,
            ...AGENTS.filter(
              (meta) =>
                saved?.partner_codes === undefined &&
                meta.id !== "general" &&
                rows.some((row) => row.agent_id === meta.numericId),
            ).map((meta) => meta.id),
          ]),
        ],
        lists: Object.fromEntries(
          state.agents.map((agent) => [
            agent.code,
            rows.filter((row) => row.agent_id === agent.id),
          ]),
        ),
      }));
    } catch (error) {
      if (owned(owner) && version === generationRef.current)
        useAgentStore.setState({ loading: false, error: message(error) });
      throw error;
    }
  })();
  bootstrapRef.current = operation;
  void operation
    .finally(() => {
      if (bootstrapRef.current === operation) bootstrapRef.current = null;
    })
    .catch(() => {});
  return operation;
}

/** 每个账号默认仅通用 Agent；伙伴添加不创建会话或调用模型。 */
export function isAgentAdded(code: AgentId): boolean {
  return code === "general" || useAgentStore.getState().partnerCodes.includes(code);
}

export async function addPartner(code: AgentId) {
  const owner = useAuthStore.getState().user?.id;
  if (!owner) throw new Error("请登录后添加伙伴。");
  await loadAgents();
  if (!owned(owner)) throw new Error("登录状态已改变。");
  const agent = useAgentStore.getState().agents.find((row) => row.code === code);
  if (!agent) throw new Error("伙伴不存在。");
  // Sidecar 同时初始化工作目录和 AGENT.md；读取已有配置不会覆盖用户提示词。
  await getAgentConfig(code);
  if (!owned(owner)) throw new Error("登录状态已改变。");
  if (isAgentAdded(code)) return;
  const state = useAgentStore.getState();
  const partnerCodes = [...new Set([...state.partnerCodes, code])];
  writeAccountCache(`agent-config:${owner}`, {
    agents: state.agents,
    skills: state.skills,
    selected: state.selected,
    partner_codes: partnerCodes,
  });
  useAgentStore.setState({ partnerCodes, agents: [...state.agents] });
}

/** 取消部门伙伴，保留其配置、工作空间和历史会话。 */
export async function removePartner(code: AgentId) {
  const owner = useAuthStore.getState().user?.id;
  if (!owner) throw new Error("请登录后管理伙伴。");
  await loadAgents();
  if (!owned(owner)) throw new Error("登录状态已改变。");
  if (code === "general") throw new Error("通用 Agent 是默认伙伴，不能取消。");
  const state = useAgentStore.getState();
  if (!state.partnerCodes.includes(code)) return;
  const partnerCodes = state.partnerCodes.filter((item) => item !== code);
  writeAccountCache(`agent-config:${owner}`, {
    agents: state.agents,
    skills: state.skills,
    selected: state.selected,
    partner_codes: partnerCodes,
  });
  useAgentStore.setState({ partnerCodes, agents: [...state.agents] });
}

export async function saveAgent(
  code: AgentId,
  changes: Pick<
    AgentConfig,
    "name" | "department" | "description" | "knowledge_base_ids" | "skill_ids"
  >,
) {
  const owner = currentOwner();
  const state = useAgentStore.getState();
  if (state.configBusy) throw new Error("配置正在保存，请稍后重试。");
  const agent = state.agents.find((row) => row.code === code);
  if (!agent) throw new Error("Agent 尚未加载。");
  useAgentStore.setState({ configBusy: true });
  try {
    // 配置暂保存为本地快照，不写入数据库。
    const updated: AgentConfig = {
      ...agent,
      ...changes,
      revision: agent.revision + 1,
    };
    if (owned(owner))
      useAgentStore.setState((state) => ({
        agents: state.agents.map((row) => (row.code === code ? updated : row)),
      }));
    return updated;
  } finally {
    if (owned(owner)) useAgentStore.setState({ configBusy: false });
  }
}
