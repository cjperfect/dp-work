import { useEffect } from "react";
import { getAccessToken, useAuthStore } from "@/stores/auth";

/** 登录后连接本机执行设备，退出时立即撤销 Main 的会话连接。 */
export function DesktopSession() {
  useEffect(() => {
    if (!window.desktop?.setSession) return;
    const sync = () => {
      void window.desktop?.setSession(getAccessToken()).catch(() => {});
    };
    sync();
    return useAuthStore.subscribe(sync);
  }, []);
  return null;
}
