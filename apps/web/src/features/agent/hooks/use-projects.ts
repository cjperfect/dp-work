import { useEffect } from "react";
import { loadProjects, useAgentProjectStore } from "@/stores/agent-projects";
import { useAuthStore } from "@/stores/auth";
export function useProjects() {
  const owner = useAuthStore((s) => s.user?.id);
  const state = useAgentProjectStore();
  useEffect(() => {
    if (owner) void loadProjects();
  }, [owner]);
  return state;
}
