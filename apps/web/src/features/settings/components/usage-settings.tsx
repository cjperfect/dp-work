import { useEffect, useState } from "react";
import { Plus, Trash2, LoaderCircle } from "lucide-react";
import { toast } from "sonner";
import type { ModelPriceDraft, UsageSettings } from "@/interfaces/settings";
import { getUsageSettings, saveUsageSettings } from "@/apis/settings";
import { useAuthStore } from "@/stores/auth";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Choice, Group, Row } from "./settings-fields";
import { usageSettingsInput } from "../lib/usage-settings";

/** 加载当前账号的单价及预算，账号切换时清理旧请求。 */
export function UsageSettingsPanel() {
  const owner = useAuthStore((state) => state.user?.id);
  const [data, setData] = useState<UsageSettings | null>(null);
  const [error, setError] = useState("");
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    let alive = true;
    setData(null);
    setError("");
    if (owner)
      void getUsageSettings()
        .then((value) => {
          if (alive) setData(value);
        })
        .catch((cause: unknown) => {
          if (alive) setError(cause instanceof Error ? cause.message : "配置读取失败。");
        });
    return () => {
      alive = false;
    };
  }, [owner, revision]);
  if (!owner) return <p className="text-sm text-muted-foreground">登录后可配置单价与预算。</p>;
  if (!data)
    return (
      <div className="flex items-center justify-between rounded-2xl border p-5 text-sm text-muted-foreground">
        {error ? (
          <>
            <span role="alert">{error}</span>
            <Button size="sm" variant="outline" onClick={() => setRevision((value) => value + 1)}>
              重试
            </Button>
          </>
        ) : (
          <span className="flex items-center gap-2">
            <LoaderCircle className="size-4 animate-spin" />
            正在读取用量配置…
          </span>
        )}
      </div>
    );
  return <UsageSettingsForm key={owner} initial={data} />;
}

/** 单价与预算采用显式保存，保留环境默认配置的回退入口。 */
function UsageSettingsForm({ initial }: { initial: UsageSettings }) {
  const initialForm = {
    enabled: initial.enabled,
    currency: initial.currency,
    token_limit: String(initial.token_limit),
    cost_limit: initial.cost_limit,
    asr_price_per_hour: initial.asr_price_per_hour ?? "",
  };
  const [form, setForm] = useState(initialForm);
  const [rows, setRows] = useState<ModelPriceDraft[]>(() =>
    Object.entries(initial.model_prices).map(([model, price]) => ({
      key: crypto.randomUUID(),
      model,
      input: price.input,
      output: price.output,
      cached_input: price.cached_input ?? "",
    })),
  );
  const snapshot = JSON.stringify({ form, rows });
  const [baseline, setBaseline] = useState(snapshot);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [remove, setRemove] = useState<string | null>(null);
  const edit = (patch: Partial<typeof form>) => {
    setForm((value) => ({ ...value, ...patch }));
    setError("");
  };
  const editPrice = (key: string, patch: Partial<ModelPriceDraft>) => {
    setRows((value) => value.map((row) => (row.key === key ? { ...row, ...patch } : row)));
    setError("");
  };
  async function save() {
    const owner = useAuthStore.getState().user?.id;
    setBusy(true);
    setError("");
    try {
      const body = usageSettingsInput(form, rows);
      await saveUsageSettings(body);
      if (useAuthStore.getState().user?.id !== owner) return;
      setBaseline(snapshot);
      toast.success("用量配置已保存，后续任务生效");
    } catch (cause) {
      if (useAuthStore.getState().user?.id === owner)
        setError(cause instanceof Error ? cause.message : "保存失败，请重试。");
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="space-y-4">
      <Group>
        <Row
          label="单价与任务预算"
          description="仅保存在当前设备，对当前账号生效。关闭后使用环境默认配置。"
        >
          <div className="flex items-center justify-end gap-3">
            <span className="text-xs text-muted-foreground">
              {form.enabled ? "个人配置" : "默认配置"}
            </span>
            <Switch
              aria-label="使用个人用量配置"
              checked={form.enabled}
              disabled={busy}
              onCheckedChange={(enabled) => edit({ enabled })}
            />
          </div>
        </Row>
      </Group>
      <fieldset disabled={busy || !form.enabled} className="min-w-0 space-y-4 disabled:opacity-55">
        <Group>
          <Row label="计价币种" description="所有单价及费用预算使用同一币种，不自动换算。">
            <Choice
              label="计价币种"
              value={form.currency}
              options={[
                { value: "CNY", label: "人民币 · CNY" },
                { value: "USD", label: "美元 · USD" },
              ]}
              onChange={(currency) => edit({ currency })}
            />
          </Row>
          <Row
            label="单次任务 Token 预算"
            description="包含主模型、子任务和对话压缩的累计输入与输出。0 表示不限制。"
          >
            <Input
              aria-label="单次任务 Token 预算"
              type="number"
              min="0"
              max="1000000000"
              step="1"
              value={form.token_limit}
              onChange={(event) => edit({ token_limit: event.target.value })}
            />
          </Row>
          <Row
            label={`单次任务费用预算（${form.currency}）`}
            description="0 表示不限制；启用前需填写当前模型单价。"
          >
            <Input
              aria-label="单次任务费用预算"
              type="number"
              min="0"
              step="any"
              value={form.cost_limit}
              onChange={(event) => edit({ cost_limit: event.target.value })}
            />
          </Row>
          <Row
            label={`ASR 单价（${form.currency} / 小时）`}
            description="留空表示未计价，0 表示免费。"
          >
            <Input
              aria-label="ASR 每小时单价"
              type="number"
              min="0"
              step="any"
              placeholder="未计价"
              value={form.asr_price_per_hour}
              onChange={(event) => edit({ asr_price_per_hour: event.target.value })}
            />
          </Row>
        </Group>
        <div className="overflow-hidden rounded-2xl border">
          <div className="flex items-center justify-between gap-3 border-b px-5 py-4">
            <div>
              <h3 className="text-sm font-medium">模型单价</h3>
              <p className="mt-1 text-xs text-muted-foreground">
                {form.currency} / 百万 Token · 模型 ID 须与调用时一致
              </p>
            </div>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => {
                setRows((value) => [
                  ...value,
                  { key: crypto.randomUUID(), model: "", input: "", output: "", cached_input: "" },
                ]);
                setError("");
              }}
            >
              <Plus className="size-3.5" />
              添加模型
            </Button>
          </div>
          {rows.length ? (
            <div className="divide-y">
              {rows.map((row, index) => (
                <div key={row.key} className="space-y-3 px-5 py-4">
                  <div className="flex items-center gap-2">
                    <Input
                      className="font-mono text-xs"
                      aria-label={`模型 ${index + 1} ID`}
                      placeholder="模型 ID"
                      value={row.model}
                      maxLength={128}
                      onChange={(event) => editPrice(row.key, { model: event.target.value })}
                    />
                    <Popover
                      open={remove === row.key}
                      onOpenChange={(open) => setRemove(open ? row.key : null)}
                    >
                      <PopoverTrigger
                        render={
                          <Button
                            type="button"
                            size="icon"
                            variant="ghost"
                            aria-label={`移除模型 ${index + 1} 单价`}
                          />
                        }
                      >
                        <Trash2 className="size-4 text-muted-foreground" />
                      </PopoverTrigger>
                      <PopoverContent align="end">
                        <p className="text-sm">移除这项模型单价？保存后生效。</p>
                        <div className="mt-3 flex justify-end gap-2">
                          <Button size="sm" variant="outline" onClick={() => setRemove(null)}>
                            取消
                          </Button>
                          <Button
                            size="sm"
                            variant="destructive"
                            onClick={() => {
                              setRows((value) => value.filter((item) => item.key !== row.key));
                              setRemove(null);
                            }}
                          >
                            移除
                          </Button>
                        </div>
                      </PopoverContent>
                    </Popover>
                  </div>
                  <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
                    {(
                      [
                        ["input", "输入"],
                        ["output", "输出"],
                        ["cached_input", "缓存输入"],
                      ] as const
                    ).map(([key, label]) => (
                      <label key={key} className="space-y-1.5 text-xs text-muted-foreground">
                        <span>{label}</span>
                        <Input
                          aria-label={`模型 ${index + 1} ${label}单价`}
                          type="number"
                          min="0"
                          step="any"
                          placeholder={key === "cached_input" ? "留空沿用输入单价" : "必填"}
                          value={row[key]}
                          onChange={(event) => editPrice(row.key, { [key]: event.target.value })}
                        />
                      </label>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <p className="px-5 py-6 text-sm text-muted-foreground">
              尚未配置模型单价，调用仍统计 Token，费用显示为未知。
            </p>
          )}
        </div>
      </fieldset>
      <p className="text-xs leading-relaxed text-muted-foreground">
        预算在下一次模型调用前检查，已发出的调用可能超出预算。修改仅影响后续新任务；运行中及待审批任务沿用原配置，历史费用不重新计算。
      </p>
      <div className="flex items-center justify-end gap-3">
        {error && (
          <p role="alert" className="mr-auto text-sm text-destructive">
            {error}
          </p>
        )}
        <Button disabled={busy || snapshot === baseline} onClick={() => void save()}>
          {busy ? <LoaderCircle className="size-3.5 animate-spin" /> : null}
          {busy ? "保存中…" : "保存配置"}
        </Button>
      </div>
    </div>
  );
}
