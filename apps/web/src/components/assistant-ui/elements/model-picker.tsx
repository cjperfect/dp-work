import { ModelSelector } from "./model-selector.aui";
import { MODELS } from "@/constants/models";
import { useAppStore } from "@/stores/app";
const models = MODELS.map((model) => ({
  id: model.id,
  name: model.label,
  description: model.description,
  icon: model.icon,
}));
export function ModelPicker() {
  const currentModel = useAppStore((state) => state.currentModel);
  const setModel = useAppStore((state) => state.setModel);
  return (
    <ModelSelector
      models={models}
      value={currentModel}
      onValueChange={setModel}
      variant="ghost"
      size="sm"
      className="h-7 px-1.5 text-xs"
    />
  );
}
