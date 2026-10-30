import { useEffect } from "react";
import { useAuthStore } from "@/stores/auth";
import { loadAgents, loadThreads, resetAgents, useAgentStore } from "@/stores/agent";
export function AgentBootstrap() {
  const owner = useAuthStore((state) => state.user?.id);
  useEffect(() => {
    if (!owner) {
      resetAgents();
      return;
    }
    void (async () => {
      try {
        await loadAgents();
        if (useAuthStore.getState().user?.id !== owner) return;
        const { agents: catalog, partnerCodes } = useAgentStore.getState();
        const agents = catalog.filter(
          (agent) => agent.code === "general" || partnerCodes.includes(agent.code),
        );
        await Promise.all(
          agents.map(async (agent) => {
            await window.desktop?.ensureAgentWorkspace?.(agent.code);
            await loadThreads(agent.code);
          }),
        );
      } catch {
        // 引导加载失败静默处理，后续用户操作会重试
      }
    })();
  }, [owner]);
  return null;
}
