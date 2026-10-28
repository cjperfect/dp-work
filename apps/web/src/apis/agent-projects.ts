import { request } from "@/lib/http";
import type { LocalProject } from "@dp-work/protocols/desktop";
import type { ThreadDetail } from "@/types/agent";
export type AgentProject = LocalProject & { created_at: string; updated_at: string };
const root = "/api/agents/projects";
export const listProjects = () => request<AgentProject[]>(root);
export const createProject = (project: LocalProject) =>
  request<AgentProject>(root, {
    method: "POST",
    data: { id: project.id, name: project.name, path: project.path, device_id: project.device_id },
  });
export const renameProject = (id: string, name: string) =>
  request<AgentProject>(`${root}/${id}`, { method: "PATCH", data: { name } });
export const removeProject = (id: string) => request<null>(`${root}/${id}`, { method: "DELETE" });
export const setConversationProject = (
  id: string,
  project_id: string | null,
  expected_revision: number,
) =>
  request<ThreadDetail>(`/api/agents/threads/${id}/project`, {
    method: "PATCH",
    data: { project_id, expected_revision },
  });
