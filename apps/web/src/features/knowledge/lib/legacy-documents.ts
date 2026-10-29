import type { KbFile } from "../constants/knowledge-data";

type LegacyBase = { id: string; files?: KbFile[] };
const storageKey = (accountId: string) => `dp-work:mock:v1:knowledge:${accountId}`;

/** 只读取已有旧文档用于迁移，不生成演示库或写入新缓存。 */
function readLegacyBases(accountId: string): LegacyBase[] {
  if (typeof localStorage === "undefined") return [];
  try {
    const raw = localStorage.getItem(storageKey(accountId));
    const value: unknown = raw ? JSON.parse(raw) : [];
    return Array.isArray(value) ? value.filter((base) => base && typeof base.id === "string") : [];
  } catch {
    return [];
  }
}

export function listLocalEditorDocuments(accountId: string, baseId: string): KbFile[] {
  const files = readLegacyBases(accountId).find((base) => base.id === baseId)?.files;
  return Array.isArray(files)
    ? files.filter(
        (file) =>
          file?.source === "editor" && typeof file.id === "string" && typeof file.name === "string",
      )
    : [];
}

/** 仅在真实服务保存成功后清理对应旧副本，迁移失败时保留原数据。 */
export function removeLocalEditorDocuments(accountId: string, baseId: string, ids: string[]) {
  if (typeof localStorage === "undefined") return;
  const bases = readLegacyBases(accountId);
  if (!bases.some((base) => base.id === baseId)) return;
  const keys = new Set(ids);
  try {
    localStorage.setItem(
      storageKey(accountId),
      JSON.stringify(
        bases.map((base) =>
          base.id === baseId && Array.isArray(base.files)
            ? {
                ...base,
                files: base.files.filter(
                  (file) => !file || file.source !== "editor" || !keys.has(file.id),
                ),
              }
            : base,
        ),
      ),
    );
  } catch {
    // 服务端已保存，保留旧副本供下次清理，不能把成功迁移误报为接口失败。
  }
}
