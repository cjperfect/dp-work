import { create } from "zustand";
import type { LocalProject } from "@dp-work/protocols/desktop";
import { toast } from "sonner";
import {
  createProject,
  listProjects,
  removeProject,
  renameProject,
  type AgentProject,
} from "@/apis/agent-projects";
import { getAccessToken, useAuthStore } from "@/stores/auth";
import { refreshProjectConversations } from "@/stores/agent";
export const useAgentProjectStore = create<{
  items: AgentProject[];
  loading: boolean;
  loaded: boolean;
  error: string | null;
}>(() => ({ items: [], loading: false, loaded: false, error: null }));
let pending: Promise<void> | null = null;
let version = 0;
useAuthStore.subscribe((state, previous) => {
  if (state.user?.id !== previous.user?.id) {
    version++;
    pending = null;
    useAgentProjectStore.setState({ items: [], loading: false, loaded: false, error: null });
  }
});
export function loadProjects(force = false): Promise<void> {
  if (!getAccessToken()) return Promise.resolve();
  if (pending) return pending;
  if (!force && useAgentProjectStore.getState().loaded) return Promise.resolve();
  const token = getAccessToken(),
    generation = version;
  const owned = () => token === getAccessToken() && generation === version;
  useAgentProjectStore.setState({ loading: true, error: null });
  const operation = listProjects()
    .then((items) => {
      if (owned()) useAgentProjectStore.setState({ items, loaded: true, loading: false });
    })
    .catch((cause: unknown) => {
      if (owned())
        useAgentProjectStore.setState({
          loading: false,
          error: cause instanceof Error ? cause.message : "项目加载失败",
        });
    })
    .finally(() => {
      if (pending === operation) pending = null;
    });
  pending = operation;
  return operation;
}
/** 选择本地文件夹，仅登记本机授权，确认创建前不写入项目列表。 */
export async function selectLocalProject() {
  if (!window.desktop?.selectProjectDirectory) throw new Error("请在桌面端选择本地工作目录。");
  const token = getAccessToken();
  const selected = await window.desktop.selectProjectDirectory();
  if (token !== getAccessToken()) throw new Error("登录状态已改变。");
  return selected;
}

export async function addLocalProject() {
  const selected = await selectLocalProject();
  return selected ? saveLocalProject(selected) : null;
}

/** 确认创建时保存名称及目录元信息。 */
export async function saveLocalProject(selected: LocalProject) {
  const token = getAccessToken(),
    generation = version;
  const project = await createProject(selected);
  if (token !== getAccessToken() || version !== generation) throw new Error("登录状态已改变。");
  version++;
  pending = null;
  useAgentProjectStore.setState((state) => ({
    loaded: true,
    loading: false,
    error: null,
    items: [project, ...state.items.filter((row) => row.id !== project.id)],
  }));
  return project;
}
export async function updateProjectName(id: string, name: string) {
  const token = getAccessToken();
  const project = await renameProject(id, name);
  if (token === getAccessToken()) {
    version++;
    pending = null;
    useAgentProjectStore.setState((state) => ({
      loading: false,
      items: state.items.map((row) => (row.id === id ? project : row)),
    }));
  }
}
export async function deleteProject(id: string) {
  const token = getAccessToken();
  await removeProject(id);
  if (token !== getAccessToken()) return;
  version++;
  pending = null;
  useAgentProjectStore.setState((state) => ({
    loading: false,
    items: state.items.filter((row) => row.id !== id),
  }));
  try {
    await refreshProjectConversations(id);
  } catch {
    toast.warning("项目已移除，会话列表刷新失败，请刷新页面。");
  }
}
