import { useEffect } from "react";
import { AgentPage } from "@/features/agent";
import { useAppStore } from "@/stores/app";
import type { AgentId } from "@/interfaces/app";

/** 保持路由选中的 Agent 与线程归属状态一致。 */
function AgentRoutePage({ agentId }: { agentId: AgentId }) {
  const setAgentId = useAppStore((state) => state.setAgentId);

  useEffect(() => {
    setAgentId(agentId);
  }, [setAgentId, agentId]);

  return <AgentPage agentId={agentId} />;
}

export function GeneralAgentPage() {
  return <AgentRoutePage agentId="general" />;
}

export function ProductAgentPage() {
  return <AgentRoutePage agentId="product" />;
}
