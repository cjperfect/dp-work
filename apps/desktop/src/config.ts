/** 校验开发页面地址。 */
export function developmentUrl(value: string): string {
  const url = new URL(value);
  const local = ["localhost", "127.0.0.1", "[::1]"].includes(url.hostname);
  if (url.username || url.password || url.protocol !== "http:" || !local)
    throw new Error("DESKTOP_WEB_URL 只允许本机 HTTP 开发地址。");
  return url.href;
}

/** 判断是否为当前应用页面。 */
export function isAppUrl(value: string, origin: string): boolean {
  try {
    return new URL(value).origin === origin;
  } catch {
    return false;
  }
}

/** 获取桌面版 Web 服务端口。 */
export function desktopPort(value = "34731"): number {
  const port = Number(value);
  if (!/^\d+$/.test(value) || !Number.isInteger(port) || port < 1024 || port > 65535)
    throw new Error("DESKTOP_WEB_PORT 必须为 1024～65535 的整数。");
  return port;
}

/** 校验业务 API 地址。 */
export function apiBaseUrl(value: string): string {
  const url = new URL(value);
  const local = ["localhost", "127.0.0.1", "[::1]"].includes(url.hostname);
  if (
    url.username ||
    url.password ||
    url.search ||
    url.hash ||
    (url.protocol !== "https:" && !(url.protocol === "http:" && local))
  )
    throw new Error("API 地址必须使用 HTTPS；本机回环地址允许 HTTP。");
  return url.href.replace(/\/$/, "");
}

/** 仅允许当前应用页面申请麦克风，不开放摄像头或屏幕采集。 */
export function canCaptureMicrophone(
  requestingUrl: string,
  origin: string,
  mediaTypes?: readonly string[],
): boolean {
  return (
    isAppUrl(requestingUrl, origin) &&
    !!mediaTypes?.length &&
    mediaTypes.every((type) => type === "audio")
  );
}
