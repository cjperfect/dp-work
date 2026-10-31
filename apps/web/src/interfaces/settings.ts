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

export type ModelPrice = { input: string; output: string; cached_input?: string };
export type UsageSettingsInput = {
  enabled: boolean;
  currency: string;
  token_limit: number;
  cost_limit: string;
  asr_price_per_hour?: string;
  model_prices: Record<string, ModelPrice>;
};
export type UsageSettings = UsageSettingsInput & { default: UsageSettingsInput };
export type ModelPriceDraft = {
  key: string;
  model: string;
  input: string;
  output: string;
  cached_input: string;
};
