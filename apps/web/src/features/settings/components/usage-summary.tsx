import type { UsageCategory } from "@/interfaces/usage";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { getUsage } from "@/apis/usage";

import { useAuthStore } from "@/stores/auth";
const names: Record<string, string> = {
  agent: "Agent 对话",
  title: "会话标题",
  memory: "自动记忆",
  minutes: "会议纪要",
  embedding: "Embedding",
  asr: "会议转写",
};
export function UsageSummary() {
  const owner = useAuthStore((state) => state.user?.id);
  const [rows, setRows] = useState<UsageCategory[]>([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    let alive = true;
    setRows([]);
    setLoading(true);
    setError("");
    void getUsage()
      .then((result) => {
        if (alive) setRows(result.items);
      })
      .catch((cause: unknown) => {
        if (alive) setError(cause instanceof Error ? cause.message : "用量读取失败。");
      })
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
    };
  }, [owner, revision]);
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-4">
        <p className="text-xs text-muted-foreground">
          当前账号在本机的新记录；仅统计接入后用量，不回填历史。ASR
          为实际发送音频时长，费用为估算，以服务商账单为准。
        </p>
        <Button
          variant="outline"
          size="sm"
          disabled={loading}
          onClick={() => setRevision((value) => value + 1)}
        >
          {loading ? "加载中…" : "刷新"}
        </Button>
      </div>
      {error ? (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      ) : !loading && !rows.length ? (
        <p className="text-sm text-muted-foreground">暂无用量记录</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="border-b text-muted-foreground">
              <tr>
                {["能力", "调用数", "已报告 Token", "音频时长", "已知估算费用"].map((label) => (
                  <th key={label} className="px-2 py-3 font-medium">
                    {label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={`${row.category}:${row.currency}`} className="border-b last:border-0">
                  <td className="px-2 py-3">{names[row.category] || row.category}</td>
                  <td className="px-2 py-3">
                    {row.calls.toLocaleString()}
                    {row.unreported_calls > 0 && (
                      <span className="block text-xs text-muted-foreground">
                        {row.unreported_calls} 次未报告完整用量
                      </span>
                    )}
                  </td>
                  <td className="px-2 py-3">
                    {row.category === "asr" ? "—" : row.total_tokens.toLocaleString()}
                  </td>
                  <td className="px-2 py-3">
                    {row.category === "asr" ? `${(row.audio_seconds / 60).toFixed(1)} 分钟` : "—"}
                  </td>
                  <td className="px-2 py-3">
                    {row.estimated_cost === null
                      ? "未计价"
                      : `${Number(row.estimated_cost).toFixed(6)} ${row.currency}`}
                    {row.unpriced_calls > 0 && (
                      <span className="block text-xs text-muted-foreground">
                        {row.unpriced_calls} 次费用未知
                      </span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
