import type { InstalledSkill, CatalogSkill } from "@/interfaces/skills";
import type { AgentId } from "@/interfaces/app";
import { http } from "@/lib/http";

/** 查询指定 Agent 已安装的技能。 */
export const listSkills = (code: AgentId) =>
  http.get<{ items: InstalledSkill[] }>("/api/skills", { params: { agent_code: code } });
/** 搜索 skills.sh 技能目录。 */
export const searchSkills = (q: string, signal?: AbortSignal) =>
  http.get<{ items: CatalogSkill[] }>("/api/skills/search", {
    params: { q },
    signal,
    timeout: 30000,
  });
/** 将市场技能安装到指定 Agent。 */
export const installSkill = (code: AgentId, source: string) =>
  http.post<InstalledSkill>(
    "/api/skills/install",
    { agent_code: code, source },
    { timeout: 130000 },
  );
/** 卸载指定 Agent 的技能。 */
export const uninstallSkill = (code: AgentId, id: string) =>
  http.post<{ removed: boolean }>("/api/skills/uninstall", { agent_code: code, skill_id: id });

/** 批量获取市场技能简介。 */
export const getSkillDescriptions = (ids: string[], signal?: AbortSignal) =>
  http.post<{ items: Record<string, string> }>(
    "/api/skills/descriptions",
    { skill_ids: ids },
    { signal, timeout: 30000 },
  );

/** 上传 SKILL.md 或技能 ZIP 到指定 Agent。 */
export async function uploadSkill(code: AgentId, file: File) {
  if (file.size > 8 * 1024 * 1024) throw new Error("技能文件不能超过 8 MB。");
  const content = await new Promise<string>((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result).split(",")[1]);
    reader.onerror = () => reject(new Error("技能文件读取失败。"));
    reader.readAsDataURL(file);
  });
  return http.post<InstalledSkill>(
    "/api/skills/upload",
    { agent_code: code, filename: file.name, content_base64: content },
    { timeout: 30000 },
  );
}
