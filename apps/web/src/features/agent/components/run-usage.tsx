import type { RunUsage as Usage } from "@/interfaces/agent";
import { useAuiState } from "@assistant-ui/react";
import { Gauge } from "lucide-react";
import { CostMeter } from "@/components/assistant-ui/elements/cost-meter";
import { formatTokenCount } from "@/components/assistant-ui/utils/tokens";
import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { uniqueRunUsage, usageLines, formatCost, sessionTokenTotals } from "../lib/usage";

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
  const session = sessionTokenTotals(runs);
  const suffix = usage.complete ? "" : "+";
  return (
    <Popover>
      <PopoverTrigger
        render={
          <Button variant="ghost" size="xs" className="ms-auto text-[11px] text-muted-foreground" />
        }
      >
        <Gauge className="size-3" />
        {known
          ? `输入 ${formatTokenCount(usage.input_tokens)}${suffix} · 输出 ${formatTokenCount(usage.output_tokens)}${suffix}`
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
            session.known
              ? `${formatTokenCount(session.total)} Token${session.complete ? "" : "+"}`
              : "用量未返回"
          }
          lines={usageLines(usage)}
        />
        <div className="grid grid-cols-2 gap-3 rounded-lg border p-3 text-xs">
          <div className="space-y-2">
            <p className="font-medium">本轮回复</p>
            <p className="flex justify-between gap-2 text-muted-foreground">
              <span>输入 Token</span>
              <span className="text-foreground tabular-nums">
                {known ? `${usage.input_tokens.toLocaleString()}${suffix}` : "—"}
              </span>
            </p>
            <p className="flex justify-between gap-2 text-muted-foreground">
              <span>输出 Token</span>
              <span className="text-foreground tabular-nums">
                {known ? `${usage.output_tokens.toLocaleString()}${suffix}` : "—"}
              </span>
            </p>
          </div>
          <div className="space-y-2 border-l pl-3">
            <p className="font-medium">会话累计</p>
            <p className="flex justify-between gap-2 text-muted-foreground">
              <span>输入 Token</span>
              <span className="text-foreground tabular-nums">
                {session.known
                  ? `${session.input.toLocaleString()}${session.complete ? "" : "+"}`
                  : "—"}
              </span>
            </p>
            <p className="flex justify-between gap-2 text-muted-foreground">
              <span>输出 Token</span>
              <span className="text-foreground tabular-nums">
                {session.known
                  ? `${session.output.toLocaleString()}${session.complete ? "" : "+"}`
                  : "—"}
              </span>
            </p>
          </div>
        </div>
        <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs text-muted-foreground">
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
          输入包含上下文和工具结果；本轮包含同一次执行中的多次模型调用，引导拆出的回复共享该轮统计。会话累计仅计算当前分支，按运行去重；“+”表示统计尚不完整。
        </p>
      </PopoverContent>
    </Popover>
  );
}
