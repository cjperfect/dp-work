export type ServiceKind = "model" | "asr";
export type ServiceConfig = {
  enabled: boolean;
  provider: "ark" | "openai" | "deepseek" | "doubao";
  base_url: string;
  model: string;
  resource_id: string;
  speaker_info: boolean;
  has_api_key: boolean;
  configured: boolean;
  default?: Partial<ServiceConfig>;
};
export type ServiceInput = Omit<ServiceConfig, "has_api_key" | "configured" | "default"> & {
  api_key?: string;
  clear_api_key?: boolean;
};
export type PersonalSettings = { model: ServiceConfig; asr: ServiceConfig };
export type ConnectionResult = { ok: boolean; message: string; latency_ms?: number };
