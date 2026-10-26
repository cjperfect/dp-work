import { create } from "zustand";
import { useAuthStore } from "@/stores/auth";

export type Theme = "light" | "dark" | "system";
type Preferences = { theme: Theme };
const defaults: Preferences = { theme: "system" };
export const usePreferences = create<Preferences>(() => defaults);
const storageKey = () => `dp-work.preferences:${useAuthStore.getState().user?.id ?? "guest"}`;

function apply() {
  if (typeof document === "undefined") return;
  const { theme } = usePreferences.getState();
  const dark =
    theme === "dark" || (theme === "system" && matchMedia("(prefers-color-scheme: dark)").matches);
  document.documentElement.classList.toggle("dark", dark);
  document.documentElement.style.colorScheme = dark ? "dark" : "light";
  document.documentElement.lang = "zh-CN";
}

/** 按当前账号恢复此设备的外观偏好。 */
export function restorePreferences() {
  let value: Preferences = defaults;
  try {
    const stored = JSON.parse(localStorage.getItem(storageKey()) ?? "null");
    if (stored)
      value = {
        theme: ["light", "dark", "system"].includes(stored.theme) ? stored.theme : "system",
      };
  } catch {
    /* 存储受限时使用默认外观。 */
  }
  usePreferences.setState(value);
  apply();
}

/** 立即应用并保存界面偏好。 */
export function updatePreferences(value: Partial<Preferences>) {
  usePreferences.setState(value);
  apply();
  try {
    localStorage.setItem(storageKey(), JSON.stringify(usePreferences.getState()));
  } catch {
    /* 当前页面仍保持所选外观。 */
  }
}

if (typeof window !== "undefined") {
  matchMedia("(prefers-color-scheme: dark)").addEventListener("change", apply);
  window.addEventListener("storage", (event) => {
    if (event.key === storageKey()) restorePreferences();
  });
  useAuthStore.subscribe((state, previous) => {
    if (state.user?.id !== previous.user?.id) restorePreferences();
  });
}
