import { useLocation } from "@tanstack/react-router";
import { useAgentStore } from "@/stores/agent";
import { useAppStore } from "@/stores/app";
import type { AgentId } from "@/interfaces/app";
export function useAgentCode(): AgentId {
  const path = useLocation({ select: (location) => location.pathname });
  const last = useAppStore((state) => state.agentId);
  const added = useAgentStore((state) => state.partnerCodes);
  return path === "/ui"
    ? "ui"
    : path === "/product"
      ? "product"
      : path === "/"
        ? "general"
        : last === "general" || added.includes(last)
          ? last
          : "general";
}
