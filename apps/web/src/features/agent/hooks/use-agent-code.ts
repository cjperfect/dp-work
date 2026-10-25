import { useLocation } from "@tanstack/react-router";
import { useAppStore } from "@/stores/app";
import type { AgentId } from "@/interfaces/app";
export function useAgentCode(): AgentId {
  const path = useLocation({ select: (location) => location.pathname });
  const last = useAppStore((state) => state.agentId);
  return path === "/product" ? "product" : path === "/" ? "general" : last;
}
