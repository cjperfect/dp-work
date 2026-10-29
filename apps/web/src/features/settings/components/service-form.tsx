import { useState } from "react";
import { Check, CircleCheck, CircleAlert, LoaderCircle } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { useAuthStore } from "@/stores/auth";
import { loadAgentModels } from "@/stores/agent-models";
import { saveService, testService } from "@/apis/settings";
import type { ServiceConfig, ServiceInput, ServiceKind, ConnectionResult } from "@/types/settings";
import { Row, Group, Choice } from "./settings-fields";

const providers = [
  { value: "ark", label: "火山方舟", url: "https://ark.cn-beijing.volces.com/api/v3" },
  { value: "openai", label: "OpenAI", url: "https://api.openai.com/v1" },
  { value: "deepseek", label: "DeepSeek", url: "https://api.deepseek.com" },
];
const errorMessage = (cause: unknown) =>
  cause instanceof Error ? cause.message : "操作失败，请重试。";

export function ServiceForm({
  kind,
  initial,
  onSaved,
}: {
  kind: ServiceKind;
  initial: ServiceConfig;
  onSaved: (value: ServiceConfig) => void;
}) {
  const inputOf = (value: ServiceConfig): ServiceInput => ({
    enabled: value.enabled,
    provider: value.provider,
    base_url:
      value.base_url ||
      (kind === "asr"
        ? "wss://openspeech.bytedance.com/api/v3/sauc/bigmodel_async"
        : providers[0].url),
    model: value.model ?? "",
    resource_id: value.resource_id ?? "volc.seedasr.sauc.duration",
    speaker_info: value.speaker_info ?? true,
  });
  const [form, setForm] = useState(() => inputOf(initial));
  const [baseline, setBaseline] = useState(() => inputOf(initial));
  const [busy, setBusy] = useState<"save" | "test" | null>(null);
  const [result, setResult] = useState<ConnectionResult | null>(null);
  const [error, setError] = useState("");
  const [hasKey, setHasKey] = useState(initial.has_api_key);
  const dirty = JSON.stringify(form) !== JSON.stringify(baseline);
  const edit = (patch: Partial<ServiceInput>) => {
    setForm((value) => ({ ...value, ...patch }));
    setResult(null);
    setError("");
  };
  const submit = async (action: "save" | "test") => {
    setBusy(action);
    setResult(null);
    setError("");
    const owner = useAuthStore.getState().user?.id;
    try {
      if (action === "test") {
        const tested = await testService(kind, form);
        if (useAuthStore.getState().user?.id === owner) setResult(tested);
      } else {
        await saveService(kind, form);
        if (useAuthStore.getState().user?.id !== owner) return;
        const nextHasKey = form.clear_api_key ? false : !!form.api_key || hasKey;
        const clean = { ...form };
        delete clean.api_key;
        delete clean.clear_api_key;
        setHasKey(nextHasKey);
        setForm(clean);
        setBaseline(clean);
        onSaved({ ...initial, ...clean, has_api_key: nextHasKey });
        if (kind === "model") void loadAgentModels(true);
        toast.success("配置已保存");
      }
    } catch (cause) {
      if (useAuthStore.getState().user?.id === owner) setError(errorMessage(cause));
    } finally {
      setBusy(null);
    }
  };
  return (
    <Group>
      <Row
        label={"使用个人配置"}
        description={"仅保存在当前设备，对当前账号生效。关闭后使用默认配置。"}
      >
        <div className="flex items-center justify-end gap-3">
          <span className="text-muted-foreground text-xs">
            {form.enabled ? "个人配置" : "平台默认"}
          </span>
          <Switch
            checked={form.enabled}
            disabled={!!busy}
            onCheckedChange={(enabled) => edit({ enabled })}
            aria-label={"使用个人配置"}
          />
        </div>
      </Row>
      <Row label={"服务商"}>
        <Choice
          label={"服务商"}
          value={form.enabled ? form.provider : (initial.default?.provider ?? form.provider)}
          disabled={!form.enabled || !!busy}
          options={
            kind === "model" ? providers : [{ value: "doubao", label: "豆包流式语音识别大模型" }]
          }
          onChange={(value) => {
            const preset = providers.find((item) => item.value === value);
            edit({
              provider: value as ServiceInput["provider"],
              api_key: undefined,
              clear_api_key: hasKey,
              ...(preset ? { base_url: preset.url, model: "" } : {}),
            });
          }}
        />
      </Row>
      <Row
        label="Base URL"
        description={
          kind === "model"
            ? "使用所选服务商的官方 HTTPS 接口地址。"
            : "豆包双向流式语音识别 WebSocket 地址。"
        }
      >
        <Input
          aria-label={`${kind} Base URL`}
          className="font-mono text-xs shadow-none"
          value={form.enabled ? form.base_url : (initial.default?.base_url ?? form.base_url)}
          disabled={!form.enabled || !!busy}
          onChange={(event) => edit({ base_url: event.target.value })}
        />
      </Row>
      {kind === "model" ? (
        <Row label={"模型 ID"} description={"填写模型 ID 或推理接入点 ID。"}>
          <Input
            aria-label={"模型 ID"}
            className="font-mono text-xs shadow-none"
            placeholder="deepseek-v4-1-flash-261017"
            value={form.enabled ? form.model : (initial.default?.model ?? form.model)}
            disabled={!form.enabled || !!busy}
            onChange={(event) => edit({ model: event.target.value })}
          />
        </Row>
      ) : (
        <>
          <Row label={"资源 ID"}>
            <Input
              aria-label={"资源 ID"}
              value={
                form.enabled ? form.resource_id : (initial.default?.resource_id ?? form.resource_id)
              }
              disabled={!form.enabled || !!busy}
              onChange={(event) => edit({ resource_id: event.target.value })}
              className="font-mono text-xs shadow-none"
            />
          </Row>
          <Row label={"区分说话人"} description={"在转写结果中标记不同的说话人。"}>
            <div className="flex justify-end">
              <Switch
                aria-label={"区分说话人"}
                checked={form.enabled ? form.speaker_info : (initial.default?.speaker_info ?? true)}
                disabled={!form.enabled || !!busy}
                onCheckedChange={(speaker_info) => edit({ speaker_info })}
              />
            </div>
          </Row>
        </>
      )}
      <Row
        label="API Key"
        description={"密钥加密保存在当前设备，不回传明文。留空保留已保存的密钥。"}
      >
        {form.enabled ? (
          <div className="flex items-center gap-2">
            <Input
              type="password"
              autoComplete="off"
              aria-label={`${kind} API Key`}
              value={form.api_key ?? ""}
              disabled={!!busy}
              placeholder={
                hasKey && !form.clear_api_key ? "已配置 · 输入新密钥替换" : "请输入 API Key"
              }
              onChange={(event) =>
                edit({ api_key: event.target.value || undefined, clear_api_key: false })
              }
              className="shadow-none"
            />
            {hasKey && (
              <Button
                size="sm"
                variant="ghost"
                disabled={!!busy}
                onClick={() => edit({ api_key: undefined, clear_api_key: !form.clear_api_key })}
              >
                {form.clear_api_key ? "撤销" : "清除"}
              </Button>
            )}
          </div>
        ) : (
          <div className="text-muted-foreground text-right text-xs">
            {initial.default?.configured ? "平台已配置" : "平台未配置"}
          </div>
        )}
      </Row>
      <div className="py-4">
        {(result || error) && (
          <p
            role="status"
            className={`mb-3 flex items-start gap-2 text-xs ${error || result?.ok === false ? "text-destructive" : "text-emerald-600 dark:text-emerald-400"}`}
          >
            {error || !result?.ok ? (
              <CircleAlert className="size-4 shrink-0" />
            ) : (
              <CircleCheck className="size-4 shrink-0" />
            )}
            <span>
              {error || result?.message}
              {result?.latency_ms != null && ` · ${result.latency_ms} ms`}
            </span>
          </p>
        )}
        <div className="flex flex-wrap items-center justify-between gap-3">
          <Button size="sm" variant="outline" disabled={!!busy} onClick={() => void submit("test")}>
            {busy === "test" && <LoaderCircle className="size-3.5 animate-spin" />}
            {"测试连接"}
          </Button>
          <div className="flex items-center gap-2">
            {dirty && (
              <>
                <span className="text-muted-foreground mr-1 text-xs">{"未保存"}</span>
                <Button
                  size="sm"
                  variant="ghost"
                  disabled={!!busy}
                  onClick={() => {
                    setForm(baseline);
                    setResult(null);
                    setError("");
                  }}
                >
                  {"取消"}
                </Button>
              </>
            )}
            <Button size="sm" disabled={!dirty || !!busy} onClick={() => void submit("save")}>
              {busy === "save" ? (
                <LoaderCircle className="size-3.5 animate-spin" />
              ) : (
                <Check className="size-3.5" />
              )}
              {"保存配置"}
            </Button>
          </div>
        </div>
        {kind === "asr" && (
          <p className="text-muted-foreground mt-3 text-xs">
            {"测试仅验证语音服务连接；麦克风权限在开始会议时申请。"}
          </p>
        )}
      </div>
    </Group>
  );
}
