import { useEffect } from "react";
import { ModelSelector } from "./model-selector.aui";
import { useAppStore } from "@/stores/app";
import { useAuthStore } from "@/stores/auth";
import { loadAgentModels, useAgentModelStore } from "@/stores/agent/agent-models";
import { Button } from "@/components/ui/button";

const EMPTY_MODELS: { id: string; name: string }[] = [];

export function ModelPicker() {
  const owner = useAuthStore((state) => state.user?.id);
  const currentModel = useAppStore((state) => state.currentModel);
  const setModel = useAppStore((state) => state.setModel);
  const { data, error, loading } = useAgentModelStore();
  const models = data?.models ?? EMPTY_MODELS;
  useEffect(() => {
    void loadAgentModels();
  }, [owner]);
  useEffect(() => {
    if (models.length && !models.some((model) => model.id === currentModel)) setModel(models[0].id);
  }, [models, currentModel, setModel]);
  if (!data?.configured || !models.length)
    return (
      <Button
        variant="ghost"
        size="sm"
        className="h-7 px-1.5 text-xs text-muted-foreground"
        disabled={!owner || loading || !error}
        title={error ?? "请在 Sidecar .env 配置模型"}
        onClick={() => void loadAgentModels(true)}
      >
        {loading ? "读取模型…" : error ? "模型加载失败，重试" : "模型未配置"}
      </Button>
    );
  return (
    <ModelSelector
      models={models}
      value={models.some((model) => model.id === currentModel) ? currentModel : models[0].id}
      onValueChange={setModel}
      variant="ghost"
      size="sm"
      className="h-7 px-1.5 text-xs"
    />
  );
}
