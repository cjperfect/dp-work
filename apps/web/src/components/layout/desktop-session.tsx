import { invalidateSkills } from "@/stores/skills";
import { useEffect } from "react";
import { getAccessToken, useAuthStore } from "@/stores/auth";

/** 登录后连接本机执行设备，退出时立即撤销 Main 的会话连接。 */
export function DesktopSession() {
  useEffect(() => {
    if (!window.desktop?.setSession) return;
    const sync = () => {
      void window.desktop?.setSession(getAccessToken()).catch(() => {});
    };
    const unsubscribeDevice = window.desktop.onDeviceConnected?.(() => invalidateSkills());
    sync();
    const unsubscribeAuth = useAuthStore.subscribe(sync);
    return () => {
      unsubscribeDevice?.();
      unsubscribeAuth();
    };
  }, []);
  return null;
}
