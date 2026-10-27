import axios, {
  type AxiosRequestConfig,
  type AxiosResponse,
  type InternalAxiosRequestConfig,
} from "axios";
import { getStoredToken } from "./token-storage";

export type RequestOptions = Omit<AxiosRequestConfig, "auth" | "url"> & {
  auth?: boolean;
};

declare module "axios" {
  interface AxiosRequestConfig {
    requiresAuth?: boolean;
    sessionToken?: string | null;
  }
}

export class HttpError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
  }
}

const handlers = new Set<(token: string | null) => void>();

/** 注册登录失效处理。 */
export function onUnauthorized(handler: (token: string | null) => void): () => void {
  handlers.add(handler);
  return () => {
    handlers.delete(handler);
  };
}

/** 通知当前会话已失效。 */
function notifyUnauthorized(token: string | null): void {
  handlers.forEach((handler) => handler(token));
}

/** 注入 Token 并记录请求所属会话。 */
async function interceptRequest(
  config: InternalAxiosRequestConfig,
): Promise<InternalAxiosRequestConfig> {
  const token = config.requiresAuth === false ? null : getStoredToken();
  config.sessionToken = token;
  if (token) {
    config.headers.set("Authorization", `Bearer ${token}`);
    try {
      const connection = await window.desktop?.setSession?.(token);
      if (connection?.deviceId) config.headers.set("X-Device-ID", connection.deviceId);
    } catch {
      /* 数据接口仍可访问，执行接口会提示设备离线。 */
    }
  }
  return config;
}

/** 处理登录失效并提取统一响应中的业务数据。 */
async function interceptResponse(response: AxiosResponse): Promise<AxiosResponse> {
  const { config, status } = response;
  let body = response.data;
  if (
    config.responseType === "stream" &&
    (status < 200 || status >= 300) &&
    typeof body?.getReader === "function"
  ) {
    try {
      body = await new Response(body).json();
    } catch {
      body = null;
    }
  }
  const token = config.sessionToken ?? null;
  if (config.requiresAuth !== false && status === 401 && getStoredToken() === token)
    notifyUnauthorized(token);
  if (status >= 200 && status < 300 && ["blob", "stream"].includes(config.responseType ?? ""))
    return response;
  if (
    status < 200 ||
    status >= 300 ||
    !body ||
    typeof body !== "object" ||
    body.code !== 0 ||
    !("data" in body)
  )
    throw new HttpError(body?.message ?? "服务暂时不可用，请稍后重试。", status);
  response.data = body.data;
  return response;
}

/** 统一处理网络异常、超时和取消。 */
function interceptResponseError(cause: unknown): never {
  throw new Error("暂时无法连接服务，请稍后重试。", { cause });
}

export const httpClient = axios.create({
  timeout: 15_000,
  validateStatus: () => true,
});

httpClient.interceptors.request.use(interceptRequest);
httpClient.interceptors.response.use(interceptResponse, interceptResponseError);

/** 通过统一 Axios 客户端请求业务接口。 */
export async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  if (!path.startsWith("/api/")) throw new Error("业务请求必须使用 /api/ 路径。");
  const { auth = true, ...config } = options;
  const response = await httpClient.request<T>({ ...config, url: path, requiresAuth: auth });
  return response.data;
}
