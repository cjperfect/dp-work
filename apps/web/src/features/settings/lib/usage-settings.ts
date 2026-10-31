import type { ModelPriceDraft, UsageSettingsInput } from "@/interfaces/settings";

/** 校验单价表单，避免重复模型被对象键静默覆盖。 */
export function usageSettingsInput(
  form: Omit<UsageSettingsInput, "model_prices" | "token_limit"> & { token_limit: string },
  rows: ModelPriceDraft[],
): UsageSettingsInput {
  const money = (value: string, label: string) => {
    if (!value.trim() || !Number.isFinite(Number(value)) || Number(value) < 0)
      throw new Error(`${label}请输入非负数字。`);
    return value.trim();
  };
  if (!/^\d+$/.test(form.token_limit) || !Number.isSafeInteger(Number(form.token_limit)))
    throw new Error("Token 预算请输入非负整数，0 表示不限制。");
  const model_prices: UsageSettingsInput["model_prices"] = {};
  for (const row of rows) {
    const model = row.model.trim();
    if (!model) throw new Error("请输入模型 ID。");
    if (Object.hasOwn(model_prices, model)) throw new Error(`模型 ${model} 重复，请合并单价配置。`);
    Object.defineProperty(model_prices, model, {
      enumerable: true,
      configurable: true,
      value: {
        input: money(row.input, "输入单价"),
        output: money(row.output, "输出单价"),
        ...(row.cached_input.trim()
          ? { cached_input: money(row.cached_input, "缓存输入单价") }
          : {}),
      },
    });
  }
  return {
    enabled: form.enabled,
    currency: form.currency,
    token_limit: Number(form.token_limit),
    cost_limit: money(form.cost_limit, "费用预算"),
    model_prices,
    ...(form.asr_price_per_hour?.trim()
      ? { asr_price_per_hour: money(form.asr_price_per_hour, "ASR 单价") }
      : {}),
  };
}
