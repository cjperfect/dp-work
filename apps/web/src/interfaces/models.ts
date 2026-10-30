import type { ReactNode } from "react";
export type ModelMeta = {
  id: string;
  label: string;
  description: string;
  /** 品牌图标（model-picker 展示用） */
  icon: ReactNode;
};
