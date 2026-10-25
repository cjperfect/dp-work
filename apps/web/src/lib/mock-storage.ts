/** 未接入业务服务时使用的本地演示存储；按模块与账号隔离。 */
export function readMock<T>(key: string): T | null {
  if (typeof localStorage === "undefined") return null;
  const raw = localStorage.getItem(`dp-work:mock:v1:${key}`);
  return raw ? (JSON.parse(raw) as T) : null;
}
export function writeMock<T>(key: string, value: T) {
  if (typeof localStorage === "undefined") return;
  localStorage.setItem(`dp-work:mock:v1:${key}`, JSON.stringify(value));
}
