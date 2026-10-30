import type { RunUsage } from "@/interfaces/agent";
import type { CostLine } from "@/components/assistant-ui/elements/cost-meter";
/** Steering 会把同一个运行分成多条回复，当前分支按 run_id 去重。 */
export function uniqueRunUsage(usages: readonly (RunUsage | undefined)[]): RunUsage[] {
  const runs = new Map<string, RunUsage>();
  for (const usage of usages) if (usage) runs.set(usage.run_id, usage);
  return [...runs.values()];
}

export function formatCost(value: string | null, currency: string): string | null {
  if (value === null) return null;
  const cost = Number(value);
  if (!Number.isFinite(cost) || cost < 0) return null;
  return `≈ ${currency} ${cost.toLocaleString("zh-CN", { minimumFractionDigits: 4, maximumFractionDigits: 6 })}`;
}

/** 模型占比按已报告 Token 计算，不把缓存和思考子项重复计入。 */
export function usageLines(usage: RunUsage): CostLine[] {
  const models = new Map<
    string,
    { input: number; output: number; cost: number; priced: boolean }
  >();
  for (const call of usage.calls) {
    if (call.status !== "reported") continue;
    const value = models.get(call.model) ?? { input: 0, output: 0, cost: 0, priced: true };
    value.input += call.input_tokens ?? 0;
    value.output += call.output_tokens ?? 0;
    value.priced &&=
      call.estimated_cost !== undefined &&
      call.status === "reported" &&
      call.currency === usage.currency;
    value.cost += Number(call.estimated_cost ?? 0);
    models.set(call.model, value);
  }
  const total = [...models.values()].reduce((sum, value) => sum + value.input + value.output, 0);
  return [...models].map(([model, value]) => ({
    model,
    inputTokens: value.input,
    outputTokens: value.output,
    cost: value.priced ? formatCost(String(value.cost), usage.currency)! : "费用未知",
    share: total ? (value.input + value.output) / total : 0,
  }));
}

/** 当前会话分支按运行去重，分别累计输入和输出；缓存、思考不重复相加。 */
export function sessionTokenTotals(usages: readonly (RunUsage | undefined)[]) {
  const runs = uniqueRunUsage(usages);
  return {
    input: runs.reduce((sum, run) => sum + run.input_tokens, 0),
    output: runs.reduce((sum, run) => sum + run.output_tokens, 0),
    total: runs.reduce((sum, run) => sum + run.total_tokens, 0),
    known: runs.some((run) => run.reported_calls > 0),
    complete: runs.length > 0 && runs.every((run) => run.complete),
  };
}
