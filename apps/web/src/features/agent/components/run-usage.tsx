import { useAuiState } from "@assistant-ui/react";
import { Gauge } from "lucide-react";
import { CostMeter } from "@/components/assistant-ui/elements/cost-meter";
import { formatTokenCount } from "@/components/assistant-ui/utils/tokens";
import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { uniqueRunUsage, usageLines, formatCost } from "../lib/usage";
import type { RunUsage as Usage } from "@/types/agent";

/** 使用 assistant-ui Cost meter 展示供应商返回的实际 Token 和可选费用估算。 */
export function RunUsage() {
  const original = useAuiState((state) => state.message.metadata.custom.usage) as Usage | undefined;
  const messages = useAuiState((state) => state.thread.messages);
  const runs = uniqueRunUsage(
    messages.map((message) => message.metadata.custom.usage as Usage | undefined),
  );
  const usage = runs.find((item) => item.run_id === original?.run_id) ?? original;
  if (!usage) return null;
  return <RunUsageView usage={usage} runs={runs} />;
}

export function RunUsageView({ usage, runs }: { usage: Usage; runs: readonly Usage[] }) {
  const known = usage.reported_calls > 0;
  const tokens = formatTokenCount(usage.total_tokens);
  const cost = formatCost(usage.estimated_cost, usage.currency);
  const total = runs.reduce((sum, run) => sum + run.total_tokens, 0);
  return (
    <Popover>
      <PopoverTrigger
        render={
          <Button variant="ghost" size="xs" className="ms-auto text-[11px] text-muted-foreground" />
        }
      >
        <Gauge className="size-3" />
        {known
          ? `${tokens} Token${usage.complete ? "" : "+"}`
          : usage.in_flight_calls
            ? "统计中…"
            : "用量未返回"}
        {cost && <span>· {cost}</span>}
      </PopoverTrigger>
      <PopoverContent
        side="top"
        align="end"
        className="w-[min(24rem,calc(100vw-2rem))] space-y-3 p-3"
      >
        <CostMeter
          className="max-w-none rounded-lg border-0 p-0 [&>div:first-child>span:first-child]:text-lg"
          runCost={cost ?? (known ? `${tokens} Token` : "未报告")}
          sessionCost={
            runs.some((run) => run.reported_calls > 0)
              ? `${formatTokenCount(total)} Token${runs.some((run) => !run.complete) ? "+" : ""}`
              : "用量未返回"
          }
          lines={usageLines(usage)}
        />
        <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs text-muted-foreground">
          <dt>输入 Token</dt>
          <dd className="text-end tabular-nums">
            {known ? usage.input_tokens.toLocaleString() : "—"}
          </dd>
          <dt>输出 Token</dt>
          <dd className="text-end tabular-nums">
            {known ? usage.output_tokens.toLocaleString() : "—"}
          </dd>
          <dt>缓存命中（包含在输入内）</dt>
          <dd className="text-end tabular-nums">
            {known && usage.cached_input_reported
              ? usage.cached_input_tokens.toLocaleString()
              : "—"}
          </dd>
          <dt>思考 Token（包含在输出内）</dt>
          <dd className="text-end tabular-nums">
            {known && usage.reasoning_reported ? usage.reasoning_tokens.toLocaleString() : "—"}
          </dd>
          <dt>模型调用</dt>
          <dd className="text-end">{usage.calls.length} 次</dd>
          {usage.token_limit !== null && (
            <>
              <dt>任务 Token 预算</dt>
              <dd className="text-end">{usage.token_limit.toLocaleString()}</dd>
            </>
          )}
          {usage.cost_limit !== null && (
            <>
              <dt>任务费用预算</dt>
              <dd className="text-end">
                {usage.currency} {usage.cost_limit}
              </dd>
            </>
          )}
        </dl>
        {!usage.complete && (
          <p className="text-xs text-muted-foreground">
            {usage.in_flight_calls
              ? "模型调用中，用量会在服务返回后更新。"
              : "部分调用未返回用量，当前仅为已知消耗；不代表零消耗。"}
          </p>
        )}
        <p className="text-xs text-muted-foreground">
          {cost
            ? "费用根据本机配置的模型单价估算，以服务商账单为准。"
            : "未配置单价或统计不完整，仅展示已报告 Token。"}
          模型条形图按 Token 占比展示。
        </p>
      </PopoverContent>
    </Popover>
  );
}
