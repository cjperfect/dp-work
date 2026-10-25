import { useEffect } from "react";
import { useAuthStore } from "@/stores/auth";
import { loadAgents, loadThreads, resetAgents } from "@/stores/agent";
export function AgentBootstrap() {
  const owner = useAuthStore((state) => state.user?.id);
  useEffect(() => {
    if (!owner) {
      resetAgents();
      return;
    }
    void loadAgents()
      .then(async () => {
        if (useAuthStore.getState().user?.id !== owner) return;
        await Promise.all([loadThreads("general"), loadThreads("product")]);
      })
      .catch(() => {});
  }, [owner]);
  return null;
}
