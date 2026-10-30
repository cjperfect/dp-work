/** 本机账号配置缓存。保留历史键前缀，避免升级后丢失已有配置。 */
export function readAccountCache<T>(key: string): T | null {
  if (typeof localStorage === "undefined") return null;
  const raw = localStorage.getItem(`dp-work:mock:v1:${key}`);
  return raw ? (JSON.parse(raw) as T) : null;
}
export function writeAccountCache<T>(key: string, value: T) {
  if (typeof localStorage === "undefined") return;
  localStorage.setItem(`dp-work:mock:v1:${key}`, JSON.stringify(value));
}
