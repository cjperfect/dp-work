import { useEffect } from "react";
import type { AgentId } from "@/interfaces/app";
import { useAuthStore } from "@/stores/auth";
import { loadSkills, useSkillsStore } from "@/stores/skills";
import type { InstalledSkill } from "@/apis/skills";
const empty: InstalledSkill[] = [];

export function useSkills(code: AgentId) {
  const owner = useAuthStore((state) => state.user?.id);
  const revision = useSkillsStore((state) => state.revision);
  const entry = useSkillsStore((state) => state.entries[code]);
  useEffect(() => {
    void loadSkills(code);
    const refresh = () => {
      void loadSkills(code);
    };
    const online = () => {
      void loadSkills(code, true);
    };
    const visible = () => {
      if (document.visibilityState === "visible") refresh();
    };
    window.addEventListener("focus", refresh);
    window.addEventListener("online", online);
    document.addEventListener("visibilitychange", visible);
    return () => {
      window.removeEventListener("focus", refresh);
      window.removeEventListener("online", online);
      document.removeEventListener("visibilitychange", visible);
    };
  }, [code, owner, revision]);
  return {
    skills: entry?.items ?? empty,
    loading: entry?.loading ?? true,
    error: entry?.error ?? null,
    reload: () => loadSkills(code, true),
  };
}
