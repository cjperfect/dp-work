import axios from "axios";
import { SIDECAR_WS } from "@/features/meetings/constants/meeting";

/** 检查转写服务与凭证配置，缺少配置时不占用麦克风。 */
export async function getSidecarAsrConfig(): Promise<{
  configured: boolean;
}> {
  const url = new URL(SIDECAR_WS);
  url.protocol = url.protocol === "wss:" ? "https:" : "http:";
  url.pathname = "/health";
  url.search = "";
  url.hash = "";
  try {
    const { data } = await axios.get(url.href, { timeout: 5000 });
    if (typeof data?.configured !== "boolean")
      throw new Error("转写服务版本不匹配，请重启 Sidecar。");
    return { configured: data.configured };
  } catch (cause) {
    if (axios.isAxiosError(cause))
      throw new Error("无法连接转写服务，请确认 Sidecar 已启动。", { cause });
    throw cause;
  }
}
