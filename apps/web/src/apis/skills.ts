import { request } from "@/lib/http";
import type { AgentId } from "@/interfaces/app";

export type InstalledSkill = {
  id: string;
  name: string;
  description: string;
  source: string;
  url: string;
};
export type CatalogSkill = InstalledSkill & { installs?: number };

export const listSkills = (code: AgentId) =>
  request<{ items: InstalledSkill[] }>("/api/skills", { params: { agent_code: code } });
export const searchSkills = (q: string, signal?: AbortSignal) =>
  request<{ items: CatalogSkill[] }>("/api/skills/search", {
    params: { q },
    signal,
    timeout: 30000,
  });
export const installSkill = (code: AgentId, source: string) =>
  request<InstalledSkill>("/api/skills/install", {
    method: "POST",
    data: { agent_code: code, source },
    timeout: 130000,
  });
export const uninstallSkill = (code: AgentId, id: string) =>
  request<{ removed: boolean }>("/api/skills/uninstall", {
    method: "POST",
    data: { agent_code: code, skill_id: id },
  });

export const getSkillDescriptions = (ids: string[], signal?: AbortSignal) =>
  request<{ items: Record<string, string> }>("/api/skills/descriptions", {
    method: "POST",
    data: { skill_ids: ids },
    signal,
    timeout: 30000,
  });
