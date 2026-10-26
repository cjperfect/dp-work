import { useSyncExternalStore } from "react";
import { usePreferences } from "@/stores/preferences";
const subscribe = (callback: () => void) => {
  const media = matchMedia("(prefers-color-scheme: dark)");
  media.addEventListener("change", callback);
  return () => media.removeEventListener("change", callback);
};
const snapshot = () => matchMedia("(prefers-color-scheme: dark)").matches;

/** 为富文本等需要明确主题的组件解析系统模式。 */
export function useResolvedTheme(): "light" | "dark" {
  const theme = usePreferences((state) => state.theme);
  const systemDark = useSyncExternalStore(subscribe, snapshot, () => false);
  return theme === "system" ? (systemDark ? "dark" : "light") : theme;
}
