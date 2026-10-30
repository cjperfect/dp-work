import type { AgentId } from "@/interfaces/app";
import type { InstalledSkill } from "@/interfaces/skills";
import { create } from "zustand";

import { useAgentStore } from "@/stores/agent";
import { listSkills } from "@/apis/skills";

import { useAuthStore, getAccessToken } from "@/stores/auth";

type Entry = {
  items: InstalledSkill[];
  loading: boolean;
  error: string | null;
  loaded: boolean;
  checkedAt: number;
};
const emptyEntry: Entry = { items: [], loading: false, error: null, loaded: false, checkedAt: 0 };
export const useSkillsStore = create<{
  entries: Partial<Record<AgentId, Entry>>;
  revision: number;
}>(() => ({
  entries: {},
  revision: 0,
}));
const pending = new Map<string, Promise<boolean>>();
let generation = 0;
const CACHE_MS = 30000;

/** 重连后保留已有内容，废弃旧请求并由正在展示的页面重新读取。 */
export function invalidateSkills() {
  generation++;
  useSkillsStore.setState((state) => ({
    revision: state.revision + 1,
    entries: Object.fromEntries(
      Object.entries(state.entries).map(([code, entry]) => [
        code,
        { ...entry, loaded: false, loading: false, checkedAt: 0 },
      ]),
    ),
  }));
}

useAuthStore.subscribe((state, previous) => {
  if (state.user?.id !== previous.user?.id) {
    useSkillsStore.setState({ entries: {} });
    pending.clear();
    generation++;
  }
});

/** 当前设备的安装结果为准，不从浏览器缓存推断技能是否可执行。 */
export function loadSkills(code: AgentId, force = false): Promise<boolean> {
  const token = getAccessToken();
  const owner = useAuthStore.getState().user?.id;
  if (!owner || !token) return Promise.resolve(false);
  const version = generation;
  const key = `${owner}:${code}:${token}:${version}`;
  const existing = pending.get(key);
  if (existing)
    return force
      ? (async () => {
          await existing;
          return generation === version &&
            useAuthStore.getState().user?.id === owner &&
            getAccessToken() === token
            ? loadSkills(code, true)
            : false;
        })()
      : existing;
  const entry = useSkillsStore.getState().entries[code] ?? emptyEntry;
  if (!force && entry.loaded && Date.now() - entry.checkedAt < CACHE_MS)
    return Promise.resolve(true);
  useSkillsStore.setState((state) => ({
    entries: { ...state.entries, [code]: { ...entry, loading: true, error: null } },
  }));
  const owned = () =>
    useAuthStore.getState().user?.id === owner &&
    getAccessToken() === token &&
    generation === version;
  const operation: Promise<boolean> = (async () => {
    try {
      const { items } = await listSkills(code);
      if (owned() && useAgentStore.getState().owner === owner) {
        useAgentStore.setState((state) => ({
          agents: state.agents.map((agent) =>
            agent.code === code ? { ...agent, skill_ids: items.map((item) => item.id) } : agent,
          ),
          skills: [
            ...state.skills.filter((skill) => !items.some((item) => item.id === skill.id)),
            ...items.map((item) => ({ ...item, department: item.source || "本机技能" })),
          ],
        }));
      }
      if (owned())
        useSkillsStore.setState((state) => ({
          entries: {
            ...state.entries,
            [code]: { items, loading: false, error: null, loaded: true, checkedAt: Date.now() },
          },
        }));
      return owned();
    } catch (cause: unknown) {
      if (owned())
        useSkillsStore.setState((state) => ({
          entries: {
            ...state.entries,
            [code]: {
              ...entry,
              loading: false,
              error: cause instanceof Error ? cause.message : "读取技能失败。",
              loaded: false,
            },
          },
        }));
      return false;
    }
  })().finally(() => {
    if (pending.get(key) === operation) pending.delete(key);
  });
  pending.set(key, operation);
  return operation;
}
