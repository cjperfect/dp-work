import { create } from "zustand";
import { getAgentModels, type AgentModels } from "@/apis/agents";
import { useAuthStore } from "@/stores/auth";

export const useAgentModelStore = create<{
  owner: number | null;
  data: AgentModels | null;
  error: string | null;
  loading: boolean;
}>(() => ({ owner: null, data: null, error: null, loading: false }));
let running: Promise<void> | null = null;
let version = 0;
export function loadAgentModels(force = false) {
  const owner = useAuthStore.getState().user?.id;
  if (!owner) return Promise.resolve();
  const state = useAgentModelStore.getState();
  if (state.owner === owner && !force && (state.data || state.error)) return Promise.resolve();
  if (running) return running;
  const requestVersion = ++version;
  useAgentModelStore.setState({ owner, loading: true, error: null });
  const operation = getAgentModels()
    .then((data) => {
      if (version === requestVersion && useAuthStore.getState().user?.id === owner)
        useAgentModelStore.setState({ data, loading: false });
    })
    .catch((cause) => {
      if (version === requestVersion && useAuthStore.getState().user?.id === owner)
        useAgentModelStore.setState({
          loading: false,
          error: cause instanceof Error ? cause.message : "模型加载失败",
        });
    })
    .finally(() => {
      if (running === operation) running = null;
    });
  running = operation;
  return operation;
}
useAuthStore.subscribe((state, previous) => {
  if (state.user?.id !== previous.user?.id) {
    version++;
    running = null;
    useAgentModelStore.setState({ owner: null, data: null, error: null, loading: false });
  }
});
