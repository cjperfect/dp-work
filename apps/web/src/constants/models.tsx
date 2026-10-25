import type { ReactNode } from "react";
import { OpenAILogo } from "@/components/assistant-ui/elements/model-icons";

/** 可用模型列表（UI 骨架：接入 Python Sidecar / 模型服务时替换为实际可用模型） */
export type ModelMeta = {
  id: string;
  label: string;
  description: string;
  /** 品牌图标（model-picker 展示用） */
  icon: ReactNode;
};

export const MODELS: ModelMeta[] = [
  {
    id: "gpt-4o",
    label: "GPT-4o",
    description: "通用能力最强，复杂推理与长文",
    icon: <OpenAILogo className="size-4" />,
  },
  {
    id: "gpt-4o-mini",
    label: "GPT-4o mini",
    description: "轻量快速，适合日常问答",
    icon: <OpenAILogo className="size-4" />,
  },
  {
    id: "o3-mini",
    label: "o3 mini",
    description: "深度推理，适合复杂任务",
    icon: <OpenAILogo className="size-4" />,
  },
  {
    id: "o1-mini",
    label: "o1 mini",
    description: "高性价比推理模型",
    icon: <OpenAILogo className="size-4" />,
  },
];
