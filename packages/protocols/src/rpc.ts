import definition from "../protocol.json";

/** 跨语言协议唯一来源，Python 直接读取同一 JSON 文件。 */
export const SIDECAR_RPC = definition;
export type RpcMethod = keyof typeof definition.methods;
export type RpcId = string;

/** 方法对应的业务参数，具体字段由 Sidecar 的业务模型校验。 */
export type RpcCallParams = Record<string, unknown>;

export interface SidecarJob {
  method: RpcMethod;
  params: RpcCallParams;
}

export interface RpcRequest {
  jsonrpc: "2.0";
  id: RpcId;
  method: RpcMethod | "system.health";
  params: RpcCallParams | Record<string, never>;
}

export interface RpcCancel {
  jsonrpc: "2.0";
  method: "$/cancelRequest";
  params: { id: RpcId };
}

export interface RpcHead {
  jsonrpc: "2.0";
  method: "stream.head";
  params: { id: RpcId; status: number; content_type: string };
}

export interface RpcChunk {
  jsonrpc: "2.0";
  method: "stream.chunk";
  params: { id: RpcId; seq: number; data: string };
}

export interface RpcHealth {
  ok: boolean;
  service: "dp-work-sidecar";
  instance_id?: string | null;
}

export interface RpcSuccess {
  jsonrpc: "2.0";
  id: RpcId;
  result: RpcHealth | { complete: true };
}

export interface RpcFailure {
  jsonrpc: "2.0";
  id: RpcId | null;
  error: { code: number; message: string };
}

export type RpcNotification = RpcHead | RpcChunk;
export type RpcMessage = RpcRequest | RpcCancel | RpcNotification | RpcSuccess | RpcFailure;

/** 验证可由本机执行的业务方法名。 */
export function isRpcMethod(value: unknown): value is RpcMethod {
  return typeof value === "string" && Object.hasOwn(definition.methods, value);
}

/** JSON 解析后的待校验帧，接收端仍需执行运行时校验。 */
export interface RpcIncomingFrame {
  jsonrpc?: string;
  id?: string;
  method?: string;
  params?: Record<string, unknown>;
  error?: unknown;
  result?: unknown;
}
